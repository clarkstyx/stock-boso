@echo off
REM ============================================================
REM  Stock Boso - one-time Windows setup
REM  Installs Python packages and creates a daily scheduled task
REM  that runs the screener at 3:35 PM Regina time. That is 5:35 PM Eastern
REM  in summer and 4:35 PM Eastern in winter: after the close either way.
REM  Monday to Friday, and appends to snapshots.csv.
REM
REM  Double-click this file from inside the stock-boso folder.
REM ============================================================

cd /d "%~dp0"
echo.
echo Stock Boso setup
echo Folder: %CD%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during install, then run this again.
  pause
  exit /b 1
)

echo Installing packages...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo Package install failed. Check your internet connection and try again.
  pause
  exit /b 1
)

echo Running the screener once to check it works...
python stock_screener.py
if errorlevel 1 (
  echo The screener hit an error. Scroll up to see it, then tell Claude.
  pause
  exit /b 1
)

echo.
echo Creating the daily scheduled task (weekdays 3:35 PM Regina, after the US close all year)...
schtasks /Create /F /TN "Stock Boso daily screen" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:35 ^
  /TR "cmd /c cd /d \"%CD%\" && python stock_screener.py > last_run.log 2>&1"
if errorlevel 1 (
  echo Could not create the task. Right-click this file and choose "Run as administrator".
  pause
  exit /b 1
)

echo.
echo Done. The screener runs every weekday at 3:35 PM. Each run:
echo   - updates screener_results.csv and .xlsx
echo   - appends new rows to snapshots.csv (one per ticker per session, never duplicated)
echo   - writes last_run.log (check it if something looks off)
echo.
echo To remove the task later:  schtasks /Delete /TN "Stock Boso daily screen" /F
echo.
pause
