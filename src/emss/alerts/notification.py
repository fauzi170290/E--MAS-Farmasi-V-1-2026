"""Notification policy uses screened classifications, never just an empty alert list."""
from dataclasses import replace
from emss.alerts.router import AlertDecision, route_alert

CLEAR_MESSAGE = 'Skrining selesai — tidak ditemukan interaksi pada basis DDI aktif'
DUPLICATE_MESSAGE = ('Terdapat potensi duplikasi obat. Pastikan apakah obat tersebut masih digunakan '
    'dan apakah pemberian atau pemberian ulang diperlukan.')


def _high_risk_message(category: str, *, has_duplicate: bool) -> str:
    message = (
        'Ditemukan interaksi kontraindikasi. Tinjau sebelum obat disiapkan.'
        if category == 'contraindicated'
        else 'Ditemukan interaksi mayor. Wajib ditinjau apoteker.'
    )
    if has_duplicate:
        message += '\nTemuan tambahan: potensi duplikasi obat. Lihat rincian obat dan resep terkait.'
    return message


def notification_decision(screening, pairs, issues, *, validated=False, validated_high_only=False):
    decision = route_alert(screening.risk_status, screening.completeness_status)
    positives = [p for p in pairs if p.classification == 'INTERACTION_FOUND']
    category = ''
    if any(p.severity_code == 'CONTRAINDICATED' for p in positives):
        category = 'contraindicated'
    elif any(p.severity_code == 'SERIOUS' for p in positives):
        category = 'major'
    elif any(p.severity_code == 'SIGNIFICANT' for p in positives):
        category = 'significant-review'
    duplicate = validated and any(
        getattr(i, 'issue_type', '') == 'DUPLICATE_THERAPY' for i in issues
    )
    duplicate_details = [getattr(i, 'message', '') for i in issues
        if getattr(i, 'issue_type', '') == 'DUPLICATE_THERAPY' and getattr(i, 'message', '')]
    duplicate_message = DUPLICATE_MESSAGE
    if duplicate_details:
        duplicate_message += '\n' + '\n'.join(
            message.removeprefix(DUPLICATE_MESSAGE).strip() for message in duplicate_details)
    high_alert = validated and any(getattr(i, 'issue_type', '') == 'HIGH_ALERT' for i in issues)
    clear = (validated and screening.risk_status == 'SAFE'
        and screening.completeness_status == 'COMPLETE' and not issues
        and screening.ingredient_count > 0 and screening.interaction_count == 0
        and screening.not_assessed_count == 0 and screening.unmapped_drug_count == 0
        and screening.pair_count == screening.assessed_no_interaction_count
        and len(pairs) == screening.pair_count
        and all(p.classification == 'ASSESSED_NO_INTERACTION' for p in pairs))
    if validated_high_only:
        if duplicate and category not in {'contraindicated', 'major'}:
            return replace(decision, level='PERSISTENT', priority=180,
                title='POTENSI DUPLIKASI OBAT — PERLU DITINJAU',
                message=duplicate_message,
                notify=True, persistent=True), 'duplicate'
        if validated and category in {'contraindicated', 'major'}:
            decision = replace(decision, level='CRITICAL' if category == 'contraindicated' else 'PERSISTENT',
                priority=300 if category == 'contraindicated' else 200,
                title='KONTRAINDIKASI' if category == 'contraindicated' else 'MAYOR',
                message=_high_risk_message(category, has_duplicate=duplicate),
                notify=True, persistent=True)
            return decision, category
        if validated and category == 'significant-review':
            return replace(decision, level='PERSISTENT', priority=120,
                title='INTERAKSI SIGNIFIKAN - WAJIB DITINJAU',
                message=('Ditemukan potensi interaksi signifikan. Rekonsiliasi obat, atur waktu minum '
                    'atau monitoring klinis sesuai konteks pasien dan dokumentasikan keputusan.'),
                notify=True, persistent=True), category
        if high_alert:
            return replace(decision, level='AUDIO', priority=150, title='Obat high-alert',
                message='Terdapat obat high-alert; periksa rincian resep.', notify=True, persistent=False), 'high-alert'
        if clear:
            return AlertDecision('AUDIO', 20, 'Pemeriksaan selesai', CLEAR_MESSAGE, True, False, False), 'screening-clear'
        # Still retain screening/issues in the queue; absence of a popup is not SAFE.
        return replace(decision, notify=False, persistent=False), ''
    if duplicate and category not in {'contraindicated', 'major'}:
        return replace(decision, level='PERSISTENT', priority=180,
            title='POTENSI DUPLIKASI OBAT — PERLU DITINJAU',
            message=duplicate_message,
            notify=True, persistent=True), 'duplicate'
    if validated and category == 'significant-review':
        return replace(decision, level='PERSISTENT', priority=120,
            title='INTERAKSI SIGNIFIKAN - WAJIB DITINJAU',
            message=('Ditemukan potensi interaksi signifikan. Lakukan rekonsiliasi, pengaturan waktu '
                'minum atau monitoring klinis sesuai konteks pasien.'),
            notify=True, persistent=True), category
    if high_alert and not category:
        return replace(decision, level='AUDIO', priority=150, title='Obat high-alert',
            message='Terdapat obat high-alert; periksa rincian resep.', notify=True, persistent=False), 'high-alert'
    if clear:
        decision = AlertDecision('AUDIO', 20, 'Skrining selesai',
            CLEAR_MESSAGE, True, False, False)
        category = 'screening-clear'
    elif validated and decision.level == 'HISTORY':
        decision = replace(decision, level='TOAST', notify=True)
    return decision, category
