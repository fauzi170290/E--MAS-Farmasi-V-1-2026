"""Read only, explicitly scoped local UAT; never an operational clinical adapter."""
from emss.config.settings import AppSettings, KhanzaAdapterMode
from emss.integrations.khanza.domain import (
    DrugMasterRow, KhanzaDataError, PrescriptionHeader, PrescriptionReference,
)
from emss.integrations.khanza.mysql import MySQLKhanzaAdapter


class LocalDummyKhanzaAdapter(MySQLKhanzaAdapter):
    code = "mysql_dummy"

    def __init__(self, settings, *, engine=None):
        # Revalidate even if the caller mutated an already validated settings object.
        AppSettings.model_validate(settings.model_dump())
        if settings.khanza_adapter != KhanzaAdapterMode.MYSQL_DUMMY:
            raise ValueError("Adapter dummy harus dipilih secara eksplisit")
        self.allowed = frozenset(settings.khanza_dummy_prescriptions)
        self._patient_scope = None
        super().__init__(settings, engine=engine)

    def _follow_scope(self):
        if self._patient_scope is None:
            params = {f'seed{i}': key for i, key in enumerate(sorted(self.allowed))}
            seed_placeholders = ','.join(':' + key for key in params)
            params['care_setting'] = self.settings.pharmacy_care_setting
            rows = self._rows(f'SELECT no_resep, no_rm, changed_at FROM `{self._header}` '
                f'WHERE no_resep IN ({seed_placeholders}) '
                'AND UPPER(asal_layanan)=:care_setting', params)
            if {str(row['no_resep']) for row in rows} != self.allowed or any(not row.get('no_rm') for row in rows):
                raise KhanzaDataError('Pasien dummy acuan tidak lengkap; cakupan tidak diperluas')
            # Bind once for this process; never silently follow a reassigned seed patient.
            patients = sorted({str(row['no_rm']) for row in rows})
            start = min(self._datetime(row['changed_at']) for row in rows).replace(hour=0, minute=0, second=0, microsecond=0)
            self._patient_scope = (patients, start)
        patients, start = self._patient_scope
        params = {f'patient{i}': key for i, key in enumerate(patients)}
        placeholders = ','.join(':' + key for key in params)
        params.update(scope_start=start.replace(tzinfo=None), first_seed=min(self.allowed),
                      care_setting=self.settings.pharmacy_care_setting)
        return (f'UPPER(h.asal_layanan)=:care_setting AND h.no_rm IN ({placeholders}) AND h.changed_at >= :scope_start '
                'AND h.no_resep >= :first_seed'), params

    def _follow_references(self, extra, extra_params, limit, order):
        where, params = self._follow_scope()
        params.update(extra_params, limit=max(1, min(limit, 500)))
        rows = self._rows(f'SELECT h.no_resep,h.changed_at,h.status_resep FROM `{self._header}` h '
            f'WHERE {where} {extra} ORDER BY {order} LIMIT :limit', params)
        return tuple(PrescriptionReference(str(row['no_resep']), '', self._datetime(row['changed_at']),
            'UJI DUMMY', str(row.get('status_resep') or '')) for row in rows)

    def _require_dummy(self, key):
        if self.settings.khanza_dummy_follow_patients:
            refs = self._follow_references('AND h.no_resep = :key', {'key': key}, 1, 'h.no_resep')
            if not refs:
                raise KhanzaDataError('Resep di luar pasien/periode dummy yang disetujui')
            return
        if key not in self.allowed:
            raise KhanzaDataError("Nomor resep di luar daftar dummy yang disetujui")

    def _references(self):
        result = []
        for key in sorted(self.allowed):
            # Do not SELECT identities, unrelated prescriptions or encounter IDs.
            rows = self._rows(
                f"SELECT no_resep, changed_at, status_resep FROM `{self._header}` "
                "WHERE no_resep = :no_resep AND UPPER(asal_layanan)=:care_setting LIMIT 1",
                {"no_resep": key, 'care_setting': self.settings.pharmacy_care_setting})
            if rows:
                row = rows[0]
                result.append(PrescriptionReference(key, "", self._datetime(row['changed_at']),
                    "UJI DUMMY", str(row.get('status_resep') or '')))
        return tuple(result)

    def scan_prescriptions(self, after_key, limit, *, since=None):
        if self.settings.khanza_dummy_follow_patients:
            extra, params = 'AND h.no_resep > :key', {'key': after_key}
            if since is not None:
                extra += ' AND h.changed_at >= :since'
                params['since'] = since.replace(tzinfo=None)
            return self._follow_references(extra, params, limit, 'h.no_resep')
        return tuple(row for row in self._references() if row.no_resep > after_key
            and (since is None or row.changed_at >= since))[:max(1, min(limit, 500))]

    def get_new_prescriptions(self, cursor, limit):
        if self.settings.khanza_dummy_follow_patients:
            extra, params = '', {}
            if cursor is not None:
                extra = 'AND (h.changed_at > :changed OR (h.changed_at = :changed AND h.no_resep > :key))'
                params = {'changed': cursor.changed_at.replace(tzinfo=None), 'key': cursor.no_resep}
            return self._follow_references(extra, params, limit, 'h.changed_at,h.no_resep')
        rows = sorted(self._references(), key=lambda row: row.cursor)
        return tuple(row for row in rows if cursor is None or row.cursor > cursor)[:max(1, min(limit, 500))]

    def latest_cursor(self):
        if self.settings.khanza_dummy_follow_patients:
            rows = self._follow_references('', {}, 1, 'h.changed_at DESC,h.no_resep DESC')
        else:
            rows = self._references()
        return max((row.cursor for row in rows), default=None)

    def get_prescription_header(self, no_resep):
        self._require_dummy(no_resep)
        name_column = ', nama_pasien' if self.settings.khanza_dummy_show_patient_name else ''
        rows = self._rows(
            f"SELECT no_resep, changed_at, status_resep, asal_layanan{name_column} FROM `{self._header}` "
            "WHERE no_resep = :no_resep AND UPPER(asal_layanan)=:care_setting LIMIT 1",
            {"no_resep": no_resep, 'care_setting': self.settings.pharmacy_care_setting})
        if not rows:
            raise KhanzaDataError("Resep dummy tidak ditemukan")
        row = rows[0]
        # Existing view has no verified final-composition contract. Never invent it.
        return PrescriptionHeader(no_resep=no_resep, no_rawat="", patient_name=str(row.get('nama_pasien') or 'PASIEN DUMMY / UJI'),
            service_unit="UJI DUMMY", changed_at=self._datetime(row['changed_at']),
            status=str(row.get('status_resep') or ''), item_basis="UNVERIFIED", composition_complete=False,
            care_setting=str(row.get('asal_layanan') or 'UNKNOWN').upper())

    def get_prescription_items(self, no_resep):
        self._require_dummy(no_resep)
        return super().get_prescription_items(no_resep)

    def get_compounded_items(self, no_resep):
        self._require_dummy(no_resep)
        return super().get_compounded_items(no_resep)

    def get_snapshot(self, no_resep):
        self._require_dummy(no_resep)
        return super().get_snapshot(no_resep)

    def get_active_drug_master(self, cursor_code="", limit=500):
        if self.settings.khanza_dummy_follow_patients:
            # Catalog contains drug codes/names only, not patient records. Prepare
            # verified code mappings for subsequent prescriptions as well.
            return super().get_active_drug_master(cursor_code, limit)
        drugs = {}
        for key in sorted(self.allowed):
            for item in self.get_snapshot(key).items:
                if item.khanza_code in drugs and drugs[item.khanza_code].display_name != item.display_name:
                    raise KhanzaDataError("Nama obat tidak konsisten pada resep dummy")
                drugs[item.khanza_code] = DrugMasterRow(item.khanza_code, item.display_name)
        return tuple(drugs[key] for key in sorted(drugs) if key > cursor_code)[:max(1, min(limit, 500))]

    def get_clinical_context(self, no_rawat):
        return {}
