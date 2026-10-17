@echo off
setlocal enabledelayedexpansion

title EasyMind AI - Local Programming Assistant

echo ============================================================
echo         EasyMind AI - Local Assistant Launcher
echo ============================================================
echo.

:: Detect Python launcher
set PYTHON_CMD=py
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    set PYTHON_CMD=python
    %PYTHON_CMD% --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [ERROR] Python was not found!
        echo Please ensure Python or the Windows 'py' launcher is installed.
        echo.
        pause
        exit /b 1
    )
)

echo [*] Detected Python launcher: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

:: Check essential dependencies
echo [*] Checking required dependencies (Flask, requests, python-dotenv)...
%PYTHON_CMD% -c "import flask, requests, dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Missing one or more dependencies. Attempting to install from requirements.txt...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo If you are offline, ensure packages were cached beforehand:
        echo   %PYTHON_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo [*] Dependencies verified successfully.
echo.
echo [*] Launching EasyMind AI Local Web Dashboard...
echo [*] Address: http://127.0.0.1:5000
echo.
echo [*] NOTE: Ensure LM Studio is running on port 1234 with a model loaded!
echo.

:: Wait 2 seconds and open browser automatically
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:5000"

:: Start Flask application
%PYTHON_CMD% app.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Server stopped or exited with an error.
    pause
)
