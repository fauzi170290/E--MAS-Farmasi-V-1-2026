@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%EMSS_BUILD_PYTHON%"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\.venv-build313\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\..\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Python virtual environment tidak ditemukan: %PYTHON_EXE%
    exit /b 1
)

cd /d "%PROJECT_DIR%"
rem A fixed temp path can stay locked by a finished Qt/Windows process and
rem falsely fail every subsequent qualification.  Each release test run gets
rem its own disposable workspace; the application data directory is unchanged.
set "TEST_TEMP=%PROJECT_DIR%\outputs\test-temp-release-%RANDOM%%RANDOM%"
if not exist "%TEST_TEMP%" mkdir "%TEST_TEMP%"
set "TEMP=%TEST_TEMP%"
set "TMP=%TEST_TEMP%"
set "QT_QPA_PLATFORM=offscreen"
"%PYTHON_EXE%" -m coverage run -m pytest --basetemp="%TEST_TEMP%" -p no:cacheprovider
if errorlevel 1 exit /b %ERRORLEVEL%
"%PYTHON_EXE%" -m coverage report
exit /b %ERRORLEVEL%
