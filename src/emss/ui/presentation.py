"""Display-only labels. Persisted status codes and clinical rules are unchanged."""
from datetime import datetime, UTC

STATUS_LABELS = {
    'NEW': 'Belum ditinjau', 'REVIEWED': 'Sudah ditinjau',
    'CRITICAL': 'Risiko kritis', 'HIGH_RISK': 'Risiko tinggi',
    'REVIEW': 'Perlu ditinjau', 'INFO': 'Informasi',
    'SAFE': 'Tidak ditemukan pada data dinilai',
    'UNMAPPED': 'Kandungan obat belum terpetakan',
    'NOT_ASSESSED': 'Pasangan obat belum dinilai',
    'PAIR_NOT_ASSESSED': 'Pasangan obat belum dinilai',
    'NOT_ASSESSABLE': 'Belum dapat dinilai', 'EXCLUDED': 'Dikecualikan dari penilaian',
    'INCOMPLETE': 'Data belum lengkap', 'COMPLETE': 'Data lengkap',
    'ERROR': 'Pemeriksaan gagal', 'FAILED': 'Pemeriksaan gagal',
    'DEAD_LETTER': 'Gagal berulang — perlu ditangani',
    'NONE': 'Tidak ada', 'MAJOR': 'Mayor', 'CONTRAINDICATED': 'Kontraindikasi',
    'MODERATE': 'Signifikan', 'MINOR': 'Minor',
    'INTERACTION_FOUND': 'Interaksi ditemukan', 'NO_INTERACTION_FOUND': 'Tidak ditemukan pada data dinilai',
    'NO_INTERACTION_REPORTED': 'Tidak ada interaksi dilaporkan',
    'DRAFT': 'DRAFT — belum disetujui', 'PUBLISHED': 'Dipublikasikan',
    'PENDING_REVIEW': 'Menunggu tinjauan', 'APPROVED': 'Disetujui',
    'MAPPED': 'Kandungan terpetakan', 'HOLD': 'Tertunda — perlu tinjauan',
    'PERSISTENT': 'Tetap tampil', 'HISTORY': 'Riwayat', 'TOAST': 'Notifikasi',
    'NO_REVIEW_REQUIRED': 'Tanpa penanda tinjauan', 'SERIOUS': 'Mayor', 'SIGNIFICANT': 'Signifikan',
    'ASSESSED_NO_INTERACTION': 'Tidak ditemukan interaksi pada basis yang dinilai',
    'CONTEXT_PENDING': 'Evaluasi ulang konteks sedang dijadwalkan',
}


def status_text(code: object) -> str:
    value = str(code)
    return STATUS_LABELS.get(value, value)


def local_time(value: str) -> str:
    if not value:
        return 'Belum ada'
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone().strftime('%d/%m %H:%M:%S')
    except ValueError:
        return value


def monitoring_text(status, active: bool) -> str:
    if status.adapter == 'disabled':
        connection = 'Koneksi Khanza belum diatur'
    elif status.adapter == 'mock':
        connection = 'SIMULASI DUMMY — bukan koneksi Khanza'
    elif status.connection_status == 'CONNECTED':
        connection = 'Terhubung ke Khanza' + (' lokal (uji dummy)' if status.adapter == 'mysql_dummy' else '')
    else:
        connection = 'Khanza belum terhubung: ' + status.connection_status
    schedule = 'Pemeriksaan otomatis aktif' if active else 'Pemeriksaan otomatis berhenti'
    result = f'{connection}  ·  {schedule}\nPembacaan berhasil terakhir: {local_time(status.last_success_at)}'
    if status.last_error:
        result += '\nPemeriksaan gagal: ' + status.last_error
    return result
