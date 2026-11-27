@echo off
rem twbdoc Live CI: watch the workbook open in Tableau Studio and show the
rem documentation and CI findings on a local dashboard (http://127.0.0.1:8765/).
rem Drop a .twbx / .twb on this bat to watch a saved file instead.
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\live_ci.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
