@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%PROJECT_DIR%\..\.venv\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo Python virtual environment tidak ditemukan: %PYTHON_EXE%
    exit /b 1
)

set "PYTHONPATH=%PROJECT_DIR%\src"
"%PYTHON_EXE%" -m emss %*
exit /b %ERRORLEVEL%
