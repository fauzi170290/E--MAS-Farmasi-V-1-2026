"""Load and diagnose the Khanza credential without copying it into process env."""
import os


def machine_credential():
    if os.name != 'nt':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment') as key:
            value = winreg.QueryValueEx(key, 'EMSS_KHANZA_PASSWORD')[0]
        return value or None
    except OSError:
        return None


def connection_password():
    """Prefer Machine so a Desktop launch cannot retain stale credentials."""
    return machine_credential() or os.environ.get('EMSS_KHANZA_PASSWORD')


def credential_diagnostic():
    process = os.environ.get('EMSS_KHANZA_PASSWORD')
    machine = machine_credential()
    if machine:
        if process and machine != process:
            return ('Environment proses berbeda dari Machine. Adapter memakai nilai Machine terbaru; '
                    'nilai tidak ditampilkan.')
        return 'Password Machine tersedia; nilai tidak ditampilkan. Koneksi tetap harus diuji.'
    if process:
        return 'Password proses tersedia; nilai Machine tidak dapat diperiksa. Koneksi tetap harus diuji.'
    return 'Password belum tersedia. Minta IT mengatur EMSS_KHANZA_PASSWORD tingkat Machine.'
