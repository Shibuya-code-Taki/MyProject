@echo off
cd /d "%~dp0"
echo.
echo =======================================================
echo   Stems Pro - ROG Local GPU Processor Setup
echo =======================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    echo         https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python found
echo.

REM Create venv
if not exist "venv" (
    echo [*] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
    echo [OK] venv created
) else (
    echo [OK] venv already exists
)
echo.

REM Activate
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate venv
    pause
    exit /b 1
)

echo [*] Upgrading pip...
python -m pip install --upgrade pip -q

echo [*] Installing PyTorch with CUDA...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

echo [*] Installing demucs...
pip install demucs

echo [*] Installing other dependencies...
pip install pycryptodome requests librosa

echo.
echo =======================================================
echo   Setup complete!
echo.
echo   Verify GPU:
echo     venv\Scripts\python -c "import torch; print(torch.cuda.is_available())"
echo.
echo   Start processor:
echo     run.bat              (process all pending, then exit)
echo     run.bat --watch      (keep watching for new songs)
echo =======================================================
pause
