@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "RUNNER=%PROJECT_DIR%\scripts\run_dev.bat"
set "CONFIG=%PROJECT_DIR%\config.example.toml"
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\E-MAS Farmasi.lnk"

if not exist "%RUNNER%" (
    echo Runner tidak ditemukan: %RUNNER%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell = New-Object -ComObject WScript.Shell; " ^
  "$shortcut = $shell.CreateShortcut('%SHORTCUT%'); " ^
  "$shortcut.TargetPath = '%RUNNER%'; " ^
  "$shortcut.Arguments = '--config ""%CONFIG%"" gui'; " ^
  "$shortcut.WorkingDirectory = '%PROJECT_DIR%'; " ^
  "$shortcut.Description = 'E-MAS Farmasi'; " ^
  "$shortcut.Save()"

if errorlevel 1 exit /b 1
echo Autostart terpasang: %SHORTCUT%
exit /b 0
