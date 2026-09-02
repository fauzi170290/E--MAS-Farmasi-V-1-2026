@echo off
setlocal
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\E-MAS Farmasi.lnk"

if exist "%SHORTCUT%" (
    del /q "%SHORTCUT%"
    if errorlevel 1 exit /b 1
    echo Autostart dihapus: %SHORTCUT%
) else (
    echo Autostart tidak ditemukan; tidak ada perubahan.
)
exit /b 0
