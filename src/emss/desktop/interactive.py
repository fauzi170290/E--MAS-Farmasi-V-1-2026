"""Prevent a user UAT GUI from owning its instance lock on an invisible test desktop.

This only inspects the current process context. It never opens or switches to
another desktop, and it does not change Windows permissions.
"""
import os
import sys


class DesktopLaunchError(RuntimeError):
    pass


def current_desktop_context():
    context = {'platform': sys.platform, 'qt_platform': os.environ.get('QT_QPA_PLATFORM', '')}
    if sys.platform != 'win32':
        return context
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetProcessWindowStation.restype = wintypes.HANDLE
    kernel.GetCurrentThreadId.restype = wintypes.DWORD
    user.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user.GetThreadDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

    def name(handle):
        value = ctypes.create_unicode_buffer(512)
        needed = wintypes.DWORD()
        if not user.GetUserObjectInformationW(handle, 2, value, ctypes.sizeof(value), ctypes.byref(needed)):
            raise DesktopLaunchError('Desktop Windows tidak dapat diverifikasi; GUI uji tidak dibuka.')
        return value.value

    context['window_station'] = name(user.GetProcessWindowStation())
    context['desktop'] = name(user.GetThreadDesktop(kernel.GetCurrentThreadId()))
    return context


def require_interactive_desktop():
    context = current_desktop_context()
    headless = context.get('qt_platform', '').split(':', 1)[0].casefold() in {'offscreen', 'minimal', 'vnc'}
    wrong_windows_desktop = context['platform'] == 'win32' and (
        context.get('window_station', '').casefold() != 'winsta0'
        or context.get('desktop', '').casefold() != 'default')
    if headless or wrong_windows_desktop:
        raise DesktopLaunchError(
            'GUI uji tidak boleh dibuka pada desktop terisolasi/tanpa tampilan. '
            'Jalankan JALANKAN_UJI_DUMMY_EMSS.cmd melalui File Explorer di desktop Anda. '
            'Tidak ada penguncian aplikasi atau pemantauan yang dimulai.')
    return context
