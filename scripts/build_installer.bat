@echo off
setlocal EnableExtensions
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%EMSS_BUILD_PYTHON%"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\.venv-build313\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Python virtual environment tidak ditemukan.
    exit /b 1
)
set "PYTHONPATH=%PROJECT_DIR%\src;%PYTHONPATH%"
set "QUALIFICATION_DIR=%PROJECT_DIR%\outputs\qualification"
if not exist "%QUALIFICATION_DIR%" mkdir "%QUALIFICATION_DIR%"
set "ISCC=%PROJECT_DIR%\toolchain\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" set "PATH=%PROJECT_DIR%\toolchain\Inno Setup 6;%PATH%"
set "SIGNATURE_OPTION="
if /I "%EMSS_REQUIRE_SIGNATURE%"=="1" set "SIGNATURE_OPTION=--require-signature"

"%PYTHON_EXE%" -m emss.release.qualification preflight ^
    --project-dir "%PROJECT_DIR%" ^
    --output "%QUALIFICATION_DIR%\installer-preflight.json" ^
    --require-installer
if errorlevel 1 (
    echo Installer preflight tidak lulus. Lihat outputs\qualification\installer-preflight.json
    exit /b 2
)

if not exist "%ISCC%" (
    echo Inno Setup 6 tidak ditemukan.
    exit /b 1
)
call "%PROJECT_DIR%\scripts\build_release.bat"
if errorlevel 1 exit /b 3
"%ISCC%" "%PROJECT_DIR%\installer\emss-farmasi.iss"
if errorlevel 1 exit /b 4
set "VERSION_FILE=%QUALIFICATION_DIR%\app-version.txt"
"%PYTHON_EXE%" -c "from emss import __version__; print(__version__)" > "%VERSION_FILE%"
if errorlevel 1 exit /b 5
set /p APP_VERSION=<"%VERSION_FILE%"
if not defined APP_VERSION exit /b 5
set "INSTALLER=%PROJECT_DIR%\outputs\installer\E-MAS-Farmasi-Setup-%APP_VERSION%-x64.exe"

"%PYTHON_EXE%" -m emss.release.qualification qualify ^
    --project-dir "%PROJECT_DIR%" ^
    --dist-dir "%PROJECT_DIR%\dist\E-MAS Farmasi" ^
    --installer "%INSTALLER%" ^
    --require-installer %SIGNATURE_OPTION% ^
    --output "%QUALIFICATION_DIR%\release-qualification.json"
if errorlevel 1 (
    echo Installer qualification tidak lulus. Artefak tidak boleh didistribusikan.
    exit /b 6
)
echo Installer release QUALIFIED. Lihat outputs\qualification\release-qualification.json
exit /b 0
