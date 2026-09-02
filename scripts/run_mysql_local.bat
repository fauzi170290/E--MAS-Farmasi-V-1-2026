@echo off
setlocal
if "%EMSS_KHANZA_PASSWORD%"=="" (
    for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('EMSS_KHANZA_PASSWORD','User')"`) do set "EMSS_KHANZA_PASSWORD=%%P"
)
if "%EMSS_KHANZA_PASSWORD%"=="" (
    echo Password integrasi belum tersedia.
    echo Jalankan configure_mysql_local.bat terlebih dahulu, lalu buka ulang file ini.
    pause
    exit /b 2
)
call "%~dp0run_dev.bat" --config "%~dp0..\config.mysql-local.toml" gui
exit /b %ERRORLEVEL%
