@echo off
setlocal
if "%EMSS_KHANZA_PASSWORD%"=="" (
    for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('EMSS_KHANZA_PASSWORD','User')"`) do set "EMSS_KHANZA_PASSWORD=%%P"
)
if "%EMSS_KHANZA_PASSWORD%"=="" (
    echo Password integrasi belum tersedia.
    echo Jalankan configure_mysql_local.bat terlebih dahulu.
    pause
    exit /b 2
)
echo Menjalankan e-MSS dalam SILENT PILOT.
echo Alert tray/popup operasional tidak akan ditampilkan.
call "%~dp0run_dev.bat" --config "%~dp0..\config.silent-local.toml" gui
exit /b %ERRORLEVEL%
