"""Bounded, durable polling prototype. No push, trigger or clinical write access."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta
import json
import re
import threading
from time import monotonic

from sqlalchemy import func, select, update

from emss.audit.service import AuditEvent
from emss.database.integration_models import IntegrationState
from emss.database.models import AppUser, Role, UserRole
from emss.database.monitoring_models import MonitorCheckpoint, MonitorEvent, MonitorInbox
from emss.database.queue_models import ProcessingQueue
from emss.integrations.khanza.domain import KhanzaCursor, KhanzaConnectionError, aware_utc, read_snapshot
from emss.integrations.khanza.domain import KhanzaScopeError, KhanzaScopeMismatch
from emss.utils.time import utc_now
from emss.services.monitor_lock import MonitorProcessLock
from emss.services import longitudinal
from emss.integrations.khanza.domain import PrescriptionSnapshot, PrescriptionHeader, PrescriptionItem


VALIDATED = frozenset({'DIPROSES_FARMASI', 'DISERAHKAN'})
ERROR_MESSAGES = {
    'ScreeningUnavailableError': 'KB belum PUBLISHED. Selesaikan review/publikasi melalui petugas berwenang; retry tetap tersimpan.',
    'KhanzaDataError': 'Data sumber belum lengkap/kontrak view belum sesuai. Minta IT memeriksa view; jangan menyatakan aman.',
    'SOURCE_UNVERIFIED': 'Komposisi akhir belum terverifikasi. View masih resep awal atau relasi pemberian obat ambigu.',
}
CONTRACT_RECHECK_SECONDS = 300


class KhanzaMonitor:
    def __init__(self, polling, *, clock=utc_now):
        self.polling = polling
        self.database = polling.database
        self.settings = polling.settings
        self.adapter = polling.adapter
        self.code = polling.adapter_code
        self.clock = clock
        self._lock = threading.Lock()
        self._process_lock = MonitorProcessLock(self.settings.database_dir / '.khanza-monitor.lock')
        self._last_contract_check: float | None = None

    def request_retry(self, no_resep, actor_user_id, reason):
        if not self._lock.acquire(blocking=False):
            raise ValueError('Worker sedang memproses. Tunggu lalu jadwalkan ulang retry.')
        try:
            if not self._process_lock.acquire():
                raise ValueError('Worker lain sedang memproses. Tunggu lalu jadwalkan ulang retry.')
            try:
                return self._request_retry(no_resep, actor_user_id, reason)
            finally:
                self._process_lock.release()
        finally:
            self._lock.release()

    def _request_retry(self, no_resep, actor_user_id, reason):
        if not re.fullmatch(r'[A-Za-z0-9/_-]{1,80}', no_resep) or not reason.strip():
            raise ValueError('Isi nomor resep yang valid dan alasan retry.')
        with self.database.session() as session:
            actor = session.get(AppUser, actor_user_id)
            roles = set(session.scalars(select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == actor_user_id)).all())
            if (actor is None or not actor.is_active or actor.normalized_username == 'mode.farmasi'
                    or not roles.intersection({'APOTEKER', 'CLINICAL_REVIEWER', 'SUPER_ADMIN', 'IT_ADMIN'})):
                raise ValueError('Pemeriksaan ulang memerlukan akun petugas aktif yang berwenang.')
            row = self._ensure_inbox(session, no_resep, 'TARGETED', 100)
            row.state = 'PENDING'
            row.next_attempt_at = self.clock()
            row.stable_since = None  # Explicit retry still requires two new observations.
            self.polling.queue.audit.append(session, AuditEvent(category='INTEGRATION',
                action='TARGETED_RETRY_REQUESTED', outcome='SUCCESS', actor_user_id=actor_user_id,
                entity_type='monitor_inbox', details={'reason': reason[:500], 'adapter': self.code,
                    'no_resep': no_resep, 'care_setting': self.settings.pharmacy_care_setting}))
            session.commit()

    def summary(self):
        with self.database.session() as session:
            counts = dict(session.execute(select(MonitorInbox.state, func.count())
                .where(MonitorInbox.adapter_code == self.code).group_by(MonitorInbox.state)).all())
            lanes = dict(session.execute(select(MonitorInbox.lane, func.count())
                .where(MonitorInbox.adapter_code == self.code, MonitorInbox.state != 'COMPLETED')
                .group_by(MonitorInbox.lane)).all())
            latest = session.scalar(select(func.max(MonitorEvent.completed_at))
                .where(MonitorEvent.adapter_code == self.code))
            errors = session.scalars(select(MonitorInbox.error_code).where(
                MonitorInbox.adapter_code == self.code, MonitorInbox.error_code != '').distinct()).all()
            return {'states': counts, 'backlog': lanes, 'last_result': str(latest or '-'),
                'errors': [ERROR_MESSAGES.get(e, 'Proses gagal; retry tersimpan. Hubungi IT dengan kode ' + e) for e in errors]}

    def progress(self, limit=100):
        with self.database.session() as session:
            rows = session.scalars(select(MonitorInbox).where(MonitorInbox.adapter_code == self.code)
                .order_by(MonitorInbox.last_seen_at.desc(), MonitorInbox.no_resep).limit(limit)).all()
            return [(r.no_resep, r.source_status or '-', r.state, str(r.attempts),
                ERROR_MESSAGES.get(r.error_code, r.error_code)) for r in rows]

    def next_poll_delay_ms(self):
        """Wake for a stable-read deadline, not another whole discovery interval."""
        regular = self.settings.khanza_poll_interval_seconds * 1000
        with self.database.session() as session:
            deadline = session.scalar(select(func.min(MonitorInbox.next_attempt_at)).where(
                MonitorInbox.adapter_code == self.code, MonitorInbox.state == 'STABILIZING'))
            state = session.get(IntegrationState, self.code)
            if state and state.next_retry_at and aware_utc(state.next_retry_at) > self.clock():
                return regular  # Reconnect backoff remains authoritative in cycle().
        if deadline is None:
            return regular
        return max(100, min(regular, int((aware_utc(deadline) - self.clock()).total_seconds() * 1000) + 1))

    def cycle(self, actor_user_id, *, force=False, on_result=None):
        from emss.services.khanza_polling import PollingResult
        if self.adapter is None:
            return PollingResult('NOT_CONFIGURED', message='Adapter belum diaktifkan')
        if self.settings.pharmacy_scope_required and self.settings.pharmacy_care_setting not in {'RALAN', 'RANAP'}:
            return PollingResult('SCOPE_NOT_READY', message='Pilih Rawat Jalan atau Rawat Inap saat masuk Mode Farmasi terlebih dahulu.')
        if not self._lock.acquire(blocking=False):
            return PollingResult('BUSY', message='Pemantauan sedang berjalan')
        try:
            acquired = self._process_lock.acquire()
        except OSError:
            self._lock.release()
            raise
        if not acquired:
            self._lock.release()
            return PollingResult('BUSY', message='Worker lain sedang memantau database ini')
        run = None
        processed = stable = failed = incomplete = detected = 0
        ids = []
        try:
            state = self.polling._state()
            if not force and state.next_retry_at and aware_utc(state.next_retry_at) > self.clock():
                return PollingResult('BACKOFF', message='Menunggu reconnect; hasil lama bukan status koneksi terkini')
            with self.database.session() as session:
                actor = session.get(AppUser, actor_user_id)
                if not self._actor_allowed(actor):
                    raise ValueError('Sesi pengguna aktif diperlukan untuk pemantauan')
            self._check_source_health(state.connection_status)
            self.polling._mark_connected()
            cursor = KhanzaCursor(state.cursor_changed_at, state.cursor_no_resep) if state.cursor_changed_at and state.cursor_no_resep else None
            run = self.polling._start_run(cursor)
            detected = self._discover()
            now = self.clock()
            with self.database.session() as session:
                due = select(MonitorInbox).where(
                    MonitorInbox.adapter_code == self.code,
                    MonitorInbox.state.not_in(('COMPLETED', 'DEFERRED_HISTORY')),
                    MonitorInbox.next_attempt_at <= now)
                budget = self.settings.khanza_monitor_batch_size
                history_budget = max(1, budget // 5) if budget > 1 else 0
                recent = session.scalars(due.where(MonitorInbox.priority >= 70)
                    .order_by(MonitorInbox.priority.desc(), (MonitorInbox.state == 'STABILIZING').desc(), MonitorInbox.next_attempt_at, MonitorInbox.no_resep)
                    .limit(budget - history_budget)).all()
                history = session.scalars(due.where(MonitorInbox.priority < 70)
                    .order_by((MonitorInbox.state == 'STABILIZING').desc(), MonitorInbox.next_attempt_at, MonitorInbox.no_resep)
                    .limit(budget - len(recent))).all()
                keys = [r.no_resep for r in recent + history]
            for key in keys:
                try:
                    outcome, screening_id = self._observe(key, actor_user_id)
                    stable += outcome in {'COMPLETED', 'REUSED'}
                    incomplete += outcome == 'INCOMPLETE'
                    if screening_id:
                        ids.append(screening_id)
                        processed += 1
                        if on_result:
                            # Delivery errors do not turn a completed screening into a failure.
                            # AlertEvent.NEW remains in the persistent outbox for recovery.
                            try:
                                on_result(screening_id)
                            except Exception:
                                pass
                except KhanzaScopeMismatch:
                    with self.database.session() as session:
                        row = session.get(MonitorInbox, (self.code, key))
                        row.state, row.error_code = 'OUT_OF_SCOPE', 'OTHER_CARE_SETTING'
                        row.next_attempt_at = self.clock() + timedelta(seconds=60)
                        session.commit()
                except KhanzaConnectionError:
                    raise
                except Exception as exc:
                    failed += 1
                    self._failure(key, type(exc).__name__)
            self.polling._mark_connected()
            result = PollingResult('PARTIAL' if failed or incomplete else 'SUCCESS', detected,
                stable, processed, incomplete, failed, tuple(ids))
        except KhanzaScopeError as exc:
            message = str(exc)
            self.polling._mark_disconnected('KHANZA_SCOPE_NOT_READY', message)
            result = PollingResult('SCOPE_NOT_READY', message=message)
        except KhanzaConnectionError:
            self.polling._mark_disconnected('KHANZA_DISCONNECTED')
            result = PollingResult('DISCONNECTED', detected, stable, processed, incomplete,
                failed, tuple(ids), 'Koneksi terputus. Tidak ada konfirmasi tanpa interaksi baru.')
        finally:
            self._process_lock.release()
            self._lock.release()
        if run:
            self.polling._finish_run(run, result, 'KHANZA_DISCONNECTED' if result.status == 'DISCONNECTED' else None)
        return result

    def _actor_allowed(self, actor):
        return actor is not None and (actor.is_active or
            (self.settings.allow_workstation_mode and actor.normalized_username == 'mode.farmasi'))

    def _check_source_health(self, connection_status: str) -> None:
        """Keep the fast poll path light without weakening the view contract."""
        now = monotonic()
        contract_due = (
            connection_status != 'CONNECTED'
            or self._last_contract_check is None
            or now - self._last_contract_check >= CONTRACT_RECHECK_SECONDS
        )
        if contract_due:
            self.adapter.test_connection()
            self._last_contract_check = now
            return
        self.adapter.check_health()

    def _ensure_inbox(self, session, key, lane, priority, *, wake=False, recheck=False):
        row = session.get(MonitorInbox, (self.code, key))
        if row is None:
            row = MonitorInbox(adapter_code=self.code, no_resep=key, lane=lane,
                priority=priority, next_attempt_at=self.clock())
            session.add(row)
            session.flush()
        else:
            if row.state == 'DEFERRED_HISTORY' and lane in {'RECENT', 'RECONCILE'}:
                row.state = 'PENDING'
                row.next_attempt_at = self.clock()
            if priority > row.priority:
                row.priority, row.lane = priority, lane
            # The changed-at cursor is the real-time signal. A prescription that
            # changed after completion must be made due immediately, while a
            # periodic reconciliation scan must not wake completed work again.
            if wake:
                row.state = 'PENDING'
                row.next_attempt_at = self.clock()
            elif recheck and row.state == 'COMPLETED':
                row.state = 'RECHECK'
                row.next_attempt_at = self.clock()
        return row

    def _discover(self):
        detected_keys = set()
        size = self.settings.khanza_page_size
        source_now = self.adapter.source_time()
        cursor = self._bootstrap_cursor(source_now)
        recent_since = aware_utc(source_now) - timedelta(days=self.settings.khanza_recent_days)
        # Recent/reconciliation scans are safety nets. The changed-at cursor below
        # is the real-time path, so do not rescan completed recent prescriptions
        # every second.
        for lane, priority in (('RECENT', 70),):
            with self.database.session() as session:
                cp = session.get(MonitorCheckpoint, (self.code, lane))
                if cp is None:
                    cp = MonitorCheckpoint(adapter_code=self.code, lane=lane, cursor_key='', cycles=0)
                    session.add(cp)
                interval = timedelta(seconds=60 if lane == 'RECENT' else 300)
                due = bool(cp.cursor_key) or cp.updated_at is None or (
                    self.clock() - aware_utc(cp.updated_at) >= interval
                )
                if not due:
                    continue
                since = cp.cursor_time or recent_since
                refs = self.adapter.scan_prescriptions(cp.cursor_key, size, since=since)
                for ref in refs:
                    row = self._ensure_inbox(session, ref.no_resep, lane, priority)
                    # A status transition can share a second-resolution timestamp.
                    # Wake only that completed row; unchanged recent rows are not reread.
                    if row.state == 'COMPLETED' and ref.status != row.source_status:
                        row.state, row.next_attempt_at = 'RECHECK', self.clock()
                cp.cursor_key = refs[-1].no_resep if len(refs) == size else ''
                cp.cursor_time = since if cp.cursor_key else None
                cp.cycles += not bool(cp.cursor_key)
                cp.updated_at = self.clock()
                session.commit()  # Inbox and discovery checkpoint are atomic.
                detected_keys.update(ref.no_resep for ref in refs)
        self._schedule_local_reconciliation(size)
        with self.database.session() as session:
            state = session.get(IntegrationState, self.code)
            refs = self.adapter.get_new_prescriptions(cursor, size)
            for ref in refs:
                recent = aware_utc(ref.cursor.changed_at) >= (
                    aware_utc(source_now) - timedelta(days=self.settings.khanza_recent_days)
                )
                self._ensure_inbox(
                    session, ref.no_resep,
                    'RECENT' if recent else 'HISTORY',
                    90 if cursor is not None and recent else (70 if recent else 10),
                    wake=cursor is not None and recent,
                )
            if refs:
                state.cursor_changed_at, state.cursor_no_resep = refs[-1].cursor.changed_at, refs[-1].no_resep
            # Adopt pre-upgrade failures without modifying the old queue or cursor.
            old = session.scalars(select(ProcessingQueue.source_no_resep).where(
                ProcessingQueue.processing_status.in_(('FAILED', 'INCOMPLETE', 'QUEUED', 'DEAD_LETTER')),
                ~select(MonitorInbox.no_resep).where(MonitorInbox.adapter_code == self.code,
                    MonitorInbox.no_resep == ProcessingQueue.source_no_resep).exists())
                .distinct().limit(size)).all()
            for key in old:
                self._ensure_inbox(session, key, 'LEGACY_RETRY', 15)
            session.commit()
        detected_keys.update(ref.no_resep for ref in refs)
        return len(detected_keys)

    def _schedule_local_reconciliation(self, size):
        """Bound timestamp-anomaly checks to prescriptions already adopted locally."""
        with self.database.session() as session:
            cp = session.get(MonitorCheckpoint, (self.code, 'RECONCILE'))
            if cp is None:
                cp = MonitorCheckpoint(adapter_code=self.code, lane='RECONCILE',
                    cursor_key='', cycles=0)
                session.add(cp)
            due = bool(cp.cursor_key) or cp.updated_at is None or (
                self.clock() - aware_utc(cp.updated_at) >= timedelta(seconds=300)
            )
            if not due:
                return
            rows = session.scalars(select(MonitorInbox).where(
                MonitorInbox.adapter_code == self.code,
                MonitorInbox.lane == 'RECENT',
                MonitorInbox.state == 'COMPLETED',
                MonitorInbox.no_resep > cp.cursor_key,
            ).order_by(MonitorInbox.no_resep).limit(size)).all()
            for row in rows:
                row.state, row.next_attempt_at = 'RECHECK', self.clock()
            cp.cursor_key = rows[-1].no_resep if len(rows) == size else ''
            cp.cursor_time = None
            cp.cycles += not bool(cp.cursor_key)
            cp.updated_at = self.clock()
            session.commit()

    def _bootstrap_cursor(self, source_now):
        """Fast-forward an empty/stale cursor while the recent lane adopts current work."""
        cutoff = aware_utc(source_now) - timedelta(days=self.settings.khanza_recent_days)
        with self.database.session() as session:
            state = session.get(IntegrationState, self.code)
            cursor = (KhanzaCursor(state.cursor_changed_at, state.cursor_no_resep)
                if state.cursor_changed_at and state.cursor_no_resep else None)
            marker = session.get(MonitorCheckpoint, (self.code, 'H4A_INCREMENTAL'))
            if marker is None:
                deferred = session.execute(update(MonitorInbox).where(
                    MonitorInbox.adapter_code == self.code,
                    MonitorInbox.lane.in_(('HISTORY', 'RECONCILE')),
                    MonitorInbox.state.not_in(('COMPLETED', 'DEFERRED_HISTORY')),
                ).values(lane='DEFERRED_HISTORY', priority=0, state='DEFERRED_HISTORY')).rowcount
                marker = MonitorCheckpoint(adapter_code=self.code, lane='H4A_INCREMENTAL',
                    cursor_key='READY', cursor_time=cutoff, cycles=1, updated_at=self.clock())
                session.add(marker)
                self.polling.queue.audit.append(session, AuditEvent(category='INTEGRATION',
                    action='HISTORICAL_BACKLOG_DEFERRED', outcome='SUCCESS',
                    entity_type='monitor_checkpoint', details={
                        'adapter': self.code, 'deferred_local_items': deferred,
                        'recent_days': self.settings.khanza_recent_days,
                    }))
                session.commit()
            if cursor is not None and aware_utc(cursor.changed_at) >= cutoff:
                return cursor

        latest = self.adapter.latest_cursor()
        if latest is None:
            return None
        reason = 'INITIAL_BOOTSTRAP' if cursor is None else 'STALE_CURSOR_FAST_FORWARD'
        with self.database.session() as session:
            state = session.get(IntegrationState, self.code)
            state.cursor_changed_at, state.cursor_no_resep = latest.changed_at, latest.no_resep
            self.polling.queue.audit.append(session, AuditEvent(category='INTEGRATION',
                action='INCREMENTAL_CURSOR_BOOTSTRAPPED', outcome='SUCCESS',
                entity_type='integration_state', entity_id=self.code, details={
                    'adapter': self.code, 'reason': reason,
                    'recent_days': self.settings.khanza_recent_days,
                    'high_watermark': latest.serialize(),
                }))
            session.commit()
        return latest

    def _observe(self, key, actor):
        # A source revision wakes dependent owners durably. Re-evaluate their
        # saved snapshots locally; no full source reread or synthetic source event.
        with self.database.session() as session:
            pending = session.get(MonitorInbox, (self.code, key))
            local_event = session.get(MonitorEvent, pending.event_id) if pending and pending.state == 'CONTEXT_PENDING' else None
            payload = longitudinal.snapshot(local_event) if local_event else None
        if payload:
            header = dict(payload['header'])
            header['changed_at'] = datetime.fromisoformat(header['changed_at']) if header.get('changed_at') else None
            snapshot = PrescriptionSnapshot(PrescriptionHeader(**header),
                tuple(PrescriptionItem(**x) for x in payload.get('regular_items', [])),
                tuple(PrescriptionItem(**x) for x in payload.get('compounded_items', [])), payload.get('revision', ''))
        else:
            snapshot = read_snapshot(self.adapter, key)
        if not self.polling.queue.allows(snapshot.header.care_setting):
            raise KhanzaScopeMismatch('Resep di luar cakupan instalasi atau asalnya belum diketahui.')
        now, fingerprint = self.clock(), snapshot.fingerprint()
        with self.database.session() as session:
            row = session.get(MonitorInbox, (self.code, key))
            row.last_seen_at = now
            final_ready = (
                snapshot.header.status in VALIDATED
                and snapshot.header.composition_complete
                and snapshot.header.item_basis == 'FINAL'
                and bool(snapshot.items)
            )
            if row.fingerprint != fingerprint:
                prior = session.get(MonitorEvent, row.event_id) if row.event_id else None
                if prior and prior.state != 'COMPLETED':
                    prior.state = 'SUPERSEDED_UNSTABLE'
                event_type = ('NEW' if not row.fingerprint else
                    'VALIDATION' if snapshot.header.status in VALIDATED and row.source_status not in VALIDATED else
                    'VALIDATION_CANCELLED' if row.source_status in VALIDATED and snapshot.header.status not in VALIDATED else 'REVISION')
                # Adding routing metadata on upgrade is not a new clinical change.
                if prior and prior.state == 'COMPLETED':
                    previous = json.loads(prior.snapshot_json)
                    current = json.loads(json.dumps(asdict(snapshot), default=str))
                    if 'care_setting' not in previous.get('header', {}):
                        current['header'].pop('care_setting', None)
                        if previous == current:
                            event_type = 'SCOPE_INITIALIZED'
                row.sequence += 1
                event = MonitorEvent(adapter_code=self.code, no_resep=key, sequence=row.sequence,
                    event_type=event_type, fingerprint=fingerprint, source_status=snapshot.header.status,
                    snapshot_json=json.dumps(asdict(snapshot), default=str, ensure_ascii=False), observed_at=now)
                session.add(event)
                session.flush()
                dependent_count = longitudinal.invalidate_dependents(session, event, prior, now)
                row.event_id, row.fingerprint = event.id, fingerprint
                row.source_status, row.stable_since = snapshot.header.status, now
                row.state, row.error_code, row.attempts = (
                    'PROCESSING' if final_ready else 'STABILIZING'
                ), '', 0
                settle_seconds = max(2, self.settings.khanza_stability_interval_seconds)
                row.next_attempt_at = now + timedelta(seconds=settle_seconds)
                self.polling.queue.audit.append(session, AuditEvent(category='INTEGRATION',
                    action='SOURCE_EVENT_OBSERVED', outcome='SUCCESS', actor_user_id=actor,
                    entity_type='monitor_event', entity_id=event.id,
                    details={'event_type': event_type, 'sequence': row.sequence, 'fingerprint': fingerprint,
                        'dependent_contexts_scheduled': dependent_count}))
                session.commit()
                # A FINAL snapshot comes from one consistent read transaction and
                # carries a validation token. It is ready for screening now; a
                # second observation only adds latency without improving integrity.
                if not final_ready:
                    return 'PENDING', None
            if row.stable_since is None:
                row.stable_since = now
                settle_seconds = (0 if snapshot.header.status in VALIDATED else
                                  max(2, self.settings.khanza_stability_interval_seconds))
                row.next_attempt_at = now + timedelta(seconds=settle_seconds)
                session.commit()
                return 'PENDING', None
            settle_seconds = (0 if snapshot.header.status in VALIDATED else
                              max(2, self.settings.khanza_stability_interval_seconds))
            if (now - aware_utc(row.stable_since)).total_seconds() < settle_seconds:
                return 'PENDING', None
            cancelled = longitudinal.is_cancelled(session.get(MonitorEvent, row.event_id))
            if not snapshot.items and not cancelled:
                row.state, row.error_code = 'INCOMPLETE', 'KhanzaDataError'
                row.next_attempt_at = now + timedelta(seconds=self.settings.khanza_poll_interval_seconds)
                session.commit()
                return 'INCOMPLETE', None
            if row.state == 'COMPLETED':
                row.next_attempt_at = now + timedelta(days=1)
                session.commit()
                return 'REUSED', None
            if row.state == 'RECHECK':
                row.state = 'COMPLETED'
                row.next_attempt_at = now + timedelta(days=1)
                session.commit()
                return 'REUSED', None
            if row.state == 'WAITING_FINAL':
                # Preliminary content is already recorded. Keep watching only
                # this not-yet-final prescription; do not screen it again.
                row.next_attempt_at = now + timedelta(
                    seconds=self.settings.khanza_poll_interval_seconds
                )
                session.commit()
                return 'REUSED', None
            event_id = row.event_id
        verified = snapshot.header.composition_complete and snapshot.header.item_basis in ('PRESCRIBED', 'FINAL')
        if cancelled:
            verified = False
        if snapshot.header.status in VALIDATED:
            verified = verified and snapshot.header.item_basis == 'FINAL'
        value = replace(self.polling._to_input(snapshot), source_event_id=event_id or '',
            source_verified=verified, source_status=snapshot.header.status)
        result = self.polling.screening.screen(value, actor, mock_mode=self.code in {'mock', 'mysql_dummy'})
        with self.database.session() as session:
            row = session.get(MonitorInbox, (self.code, key))
            event = session.get(MonitorEvent, event_id)
            row.screening_id = event.screening_id = result.screening_id
            session.commit()
        self.polling.queue.enqueue_screening(result.screening_id)
        with self.database.session() as session:
            row = session.get(MonitorInbox, (self.code, key))
            event = session.get(MonitorEvent, event_id)
            event.state = 'COMPLETED'
            row.state = 'COMPLETED' if (
                cancelled or (verified and snapshot.header.status in VALIDATED)
            ) else 'WAITING_FINAL'
            row.error_code = '' if verified else 'SOURCE_UNVERIFIED'
            event.completed_at = self.clock()
            row.next_attempt_at = self.clock() + (
                timedelta(days=1) if row.state == 'COMPLETED'
                else timedelta(seconds=self.settings.khanza_poll_interval_seconds)
            )
            session.commit()
        return 'COMPLETED', result.screening_id

    def _failure(self, key, code):
        with self.database.session() as session:
            row = session.get(MonitorInbox, (self.code, key))
            row.attempts += 1
            row.state, row.error_code = 'RETRY', code
            row.next_attempt_at = self.clock() + timedelta(seconds=min(300, 5 * 2 ** min(row.attempts - 1, 6)))
            session.commit()
