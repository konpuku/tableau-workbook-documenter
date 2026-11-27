@echo off
rem Install the twbdoc CI skill for the Tableau Agent (Tableau Studio).
rem After installing, run /reload-skills in the Tableau Agent chat.
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\install_skill.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
