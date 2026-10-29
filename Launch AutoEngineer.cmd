@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
 echo AutoEngineer Python environment not found at "%PYTHON%".
 echo Setup or repair the project's .venv before launching.
 pause
 exit /b 1
)
"%PYTHON%" "%~dp0agent\qt_desktop_entry.py"
if errorlevel 1 (
 echo AutoEngineer exited with an error. See the message above.
 pause
)
