@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found. Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python local_processor.py %*
pause
