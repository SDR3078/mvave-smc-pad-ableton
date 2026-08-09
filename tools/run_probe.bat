@echo off
REM Runs mvave_probe.py on Windows in its own virtual environment.
REM First run creates .\venv-midi and installs deps; later runs just start it.
REM Deliberately a separate venv from the capture server's, so this cannot
REM disturb a rig that already works. Teardown: delete venv-midi.
REM See docs/TEARDOWN.md.
REM
REM Usage:  run_probe.bat --list
REM         run_probe.bat --listen --port "MIDIIN3"

setlocal
cd /d "%~dp0." || goto :nocd
set "VENV=%~dp0venv-midi"
set "PY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\.deps-ok"

if not exist "%PY%" (
    echo Creating virtual environment in "%VENV%" ...
    rmdir /s /q "%VENV%" 2>nul
    python -m venv "%VENV%"
    if errorlevel 1 goto :nopython
    if not exist "%PY%" goto :nopython
)

if not exist "%STAMP%" (
    echo Installing dependencies ...
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    "%PY%" -m pip install -r "%~dp0requirements-midi.txt"
    if errorlevel 1 goto :pipfail
    "%PY%" -c "import mido, rtmidi"
    if errorlevel 1 goto :pipfail
    > "%STAMP%" echo ok
    echo.
)

"%PY%" "%~dp0mvave_probe.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Probe exited with code %RC%.
    pause
)
endlocal & exit /b %RC%

:nocd
echo Could not enter "%~dp0" ^(UNC path?^). Map it to a drive letter first.
pause
exit /b 1

:nopython
echo.
echo Could not create the virtual environment in "%VENV%".
echo Is real Python installed and on PATH?  Try:  python --version
pause
exit /b 1

:pipfail
echo.
echo Dependency install failed - check your internet connection and try again.
pause
exit /b 1
