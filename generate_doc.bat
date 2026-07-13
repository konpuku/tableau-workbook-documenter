@echo off
rem Tableau ワークブック設計書生成ツール
rem 使い方: この bat に .twbx / .twb をドラッグ&ドロップする
rem         (引数なしでダブルクリックすると同じフォルダ内の twbx を全て処理)
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\generate_doc.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
pause
exit /b %EXITCODE%
