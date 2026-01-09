@echo off
:: This script activates the local Python virtual environment and then runs the AEB application.

:: Find the directory where this script is located.
set "SCRIPT_DIR=%~dp0"

:: Define the path to the virtual environment's activation script.
set "VENV_ACTIVATE=%SCRIPT_DIR%.venv\Scripts\activate.bat"

:: Check if the virtual environment exists.
IF NOT EXIST "%VENV_ACTIVATE%" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please create it by running the following command in this directory:
    echo python -m venv .venv
    echo.
    echo After creating it, run this script again.
    pause
    exit /b 1
)

:: Activate the virtual environment. The 'CALL' command is crucial.
echo Activating virtual environment...
CALL "%VENV_ACTIVATE%"

:: Launch the application.
echo Starting Audio E-stim Bridge...
python -m aeb

echo.
echo AEB has been closed.
pause