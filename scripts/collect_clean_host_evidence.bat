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
"%PYTHON_EXE%" -m emss.release.clean_host %*
exit /b %ERRORLEVEL%
