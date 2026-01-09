@echo off
:: This script prepares and builds the AEB standalone executable using PyInstaller.

:: --- Stage 1: Environment Verification ---
echo Verifying and activating virtual environment...
set "SCRIPT_DIR=%~dp0"
set "VENV_ACTIVATE=%SCRIPT_DIR%.venv\Scripts\activate.bat"

IF NOT EXIST "%VENV_ACTIVATE%" (
    echo [FATAL ERROR] Virtual environment not found! Build cannot continue.
    echo Please create the environment first: python -m venv .venv
    pause
    exit /b 1
)

CALL "%VENV_ACTIVATE%"

:: --- Stage 2: Clean Previous Builds ---
echo Cleaning up previous build artifacts...
IF EXIST "%SCRIPT_DIR%dist" (
    rmdir /s /q "%SCRIPT_DIR%dist"
)
IF EXIST "%SCRIPT_DIR%build" (
    rmdir /s /q "%SCRIPT_DIR%build"
)
IF EXIST "%SCRIPT_DIR%AEB.spec" (
    del "%SCRIPT_DIR%AEB.spec"
)

:: --- Stage 3: Run PyInstaller ---
echo Starting the PyInstaller build process...
pyinstaller --onefile --windowed --name="AEB" ^
    --paths="." ^
    --collect-binaries="vgamepad" ^
    --hidden-import="sounddevice" ^
    --hidden-import="soundcard" ^
    --hidden-import="pynput.keyboard._win32" ^
    --hidden-import="pynput.mouse._win32" ^
    --hidden-import="scipy.signal" ^
    --hidden-import="scipy.special" ^
    aeb/__main__.py

:: --- Stage 4: Completion ---
echo.
IF EXIST "%SCRIPT_DIR%dist\AEB.exe" (
    echo [SUCCESS] Build complete! Find the executable in the 'dist' folder.
) ELSE (
    echo [FAILURE] Build process failed. Please review the output above for errors.
)
echo.
pause