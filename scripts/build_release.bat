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

cd /d "%PROJECT_DIR%"
set "PYTHONPATH=%PROJECT_DIR%\src;%PYTHONPATH%"
set "QUALIFICATION_DIR=%PROJECT_DIR%\outputs\qualification"
if not exist "%QUALIFICATION_DIR%" mkdir "%QUALIFICATION_DIR%"

"%PYTHON_EXE%" -m emss.release.qualification preflight ^
    --project-dir "%PROJECT_DIR%" ^
    --output "%QUALIFICATION_DIR%\preflight.json"
if errorlevel 1 (
    echo Release preflight tidak lulus. Lihat outputs\qualification\preflight.json
    exit /b 2
)

call "%PROJECT_DIR%\scripts\run_tests.bat"
if errorlevel 1 exit /b 3
"%PYTHON_EXE%" -m emss.release.drill ^
    --output "%QUALIFICATION_DIR%\data-lifecycle-drill.json"
if errorlevel 1 (
    echo Data lifecycle drill tidak lulus. Build dihentikan.
    exit /b 4
)
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean "%PROJECT_DIR%\emss-farmasi.spec"
if errorlevel 1 exit /b 5

"%PYTHON_EXE%" -m emss.release.qualification qualify ^
    --project-dir "%PROJECT_DIR%" ^
    --dist-dir "%PROJECT_DIR%\dist\E-MAS Farmasi" ^
    --output "%QUALIFICATION_DIR%\binary-qualification.json"
if errorlevel 1 (
    echo Binary qualification tidak lulus. Artefak tidak boleh dirilis.
    exit /b 6
)
echo Binary release QUALIFIED. Lihat outputs\qualification\binary-qualification.json
exit /b 0
