@echo off
REM Runs mvave_probe.py on Windows in its own virtual environment.
REM First run creates .\venv-midi and installs deps; later runs just start it.
REM Deliberately its own venv, so this cannot disturb any other virtualenv in
REM the project. Teardown: delete venv-midi.
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

REM The stamp is a COPY of the requirements file, not a marker, so bumping a
REM pin reinstalls instead of silently keeping the old version forever.
set "NEEDS_DEPS="
if not exist "%STAMP%" set "NEEDS_DEPS=1"
if exist "%STAMP%" (
    fc /b "%STAMP%" "%~dp0requirements-midi.txt" >nul 2>&1
    if errorlevel 1 set "NEEDS_DEPS=1"
)

if defined NEEDS_DEPS (
    echo Installing dependencies ...
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    "%PY%" -m pip install -r "%~dp0requirements-midi.txt"
    if errorlevel 1 goto :pipfail
    "%PY%" -c "import mido, rtmidi"
    if errorlevel 1 goto :importfail
    copy /y "%~dp0requirements-midi.txt" "%STAMP%" >nul
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
echo Could not DOWNLOAD the dependencies. Check your internet connection, or
echo whether a wheel exists for this Python version and architecture:
"%PY%" --version
pause
exit /b 1

:importfail
echo.
echo The dependencies installed but could not be IMPORTED. This is a runtime
echo problem, not a download one - python-rtmidi needs a working MIDI backend.
"%PY%" --version
pause
exit /b 1
