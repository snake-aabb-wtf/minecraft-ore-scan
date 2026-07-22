@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [INFO] Virtual environment not found. Creating it...
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found in PATH.
        pause
        exit /b 1
    )

    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Virtual environment found.
)

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment Python executable is missing.
    pause
    exit /b 1
)

echo [INFO] Checking dependencies...
"%VENV_PYTHON%" -c "import nbtlib, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Dependencies are already installed.
)

echo [INFO] Starting application...
"%VENV_PYTHON%" main.py
if errorlevel 1 (
    echo [ERROR] Application exited with an error.
    pause
    exit /b 1
)

endlocal
