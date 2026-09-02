@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_mysql_local.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Konfigurasi gagal. Foto pesan di atas untuk tim pengembang.
pause
exit /b %EXIT_CODE%

