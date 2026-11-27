# twbdoc CI スキルを Tableau Agent (Tableau Studio) にインストールする
# 通常は 1 つ上のフォルダの install_skill.bat を使ってください。
# 使い方: powershell -ExecutionPolicy Bypass -File app\install_skill.ps1 [-Destination <skills フォルダ>]
# インストール後、Tableau Agent のチャットで /reload-skills を実行する。
param(
    [string]$Destination = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$source = Join-Path $scriptDir 'skills\twbdoc-ci'

$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }
function T { param([string]$Ja, [string]$En) if ($script:Lang -eq 'en') { return $En }; return $Ja }

# スキルが使う Python の実体パスを返す (同梱 Python を最優先)
function Find-PythonExecutable {
    $bundled = Join-Path $scriptDir 'python\python.exe'
    if (Test-Path $bundled) { return $bundled }
    foreach ($candidate in @('py', 'python')) {
        if ($null -ne (Get-Command $candidate -ErrorAction SilentlyContinue)) {
            try {
                $executable = & $candidate -c 'import sys; print(sys.executable) if sys.version_info >= (3, 10) else None' 2>$null
                if ($LASTEXITCODE -eq 0 -and "$executable" -ne '' -and (Test-Path "$executable")) {
                    return "$executable".Trim()
                }
            } catch { continue }
        }
    }
    return $null
}

if (-not (Test-Path $source)) {
    Write-Host (T "[エラー] スキルが見つかりません: $source" "[Error] Skill not found: $source") -ForegroundColor Red
    exit 2
}
$python = Find-PythonExecutable
if ($null -eq $python) {
    Write-Host (T '[エラー] Python 3.10 以上が見つかりません。' '[Error] Python 3.10 or later was not found.') -ForegroundColor Red
    Write-Host (T '  同梱 Python (app\python) を配置するか、Python をインストールしてください。' '  Set up the bundled Python (app\python) or install Python.')
    exit 3
}
if ($Destination -eq '') {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $Destination = Join-Path $documents 'My Tableau Repository\Tableau Agent\skills'
}
$target = Join-Path $Destination 'twbdoc-ci'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force

$utf8 = New-Object System.Text.UTF8Encoding($false)
$scriptsDir = Join-Path $target 'scripts'

# スキルのスクリプトが twbdoc 本体 (この app フォルダ) を見つけられるようにする
$config = @{ twbdoc_app = $scriptDir; python = $python } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $scriptsDir 'config.json'), $config, $utf8)

# Tableau Agent が実行する起動ファイル。python が PATH に無い PC でも
# インストール時に見つけた Python (同梱 Python など) で動くようにする。
# パスに日本語 (OneDrive\ドキュメント 等) が含まれても読めるよう UTF-8 で書き、chcp 65001 で読む。
$runCmd = "@echo off`r`nchcp 65001 >nul`r`n`"$python`" `"%~dp0twbdoc_ci.py`" %*`r`nexit /b %ERRORLEVEL%`r`n"
[System.IO.File]::WriteAllText((Join-Path $scriptsDir 'run_ci.cmd'), $runCmd, $utf8)

Write-Host (T "[完了] スキルをインストールしました: $target" "[Done] Installed the skill: $target")
Write-Host (T "  使用する Python: $python" "  Python used: $python")
Write-Host (T '  Tableau Agent のチャットで /reload-skills を実行してください。' '  Run /reload-skills in the Tableau Agent chat.')
