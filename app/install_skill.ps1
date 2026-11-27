# twbdoc CI スキルを Tableau Agent (Tableau Studio) にインストールする
# 使い方: powershell -ExecutionPolicy Bypass -File app\install_skill.ps1 [-Destination <skills フォルダ>]
# インストール後、Tableau Agent のチャットで /reload-skills を実行する。
param(
    [string]$Destination = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$repoDir = Split-Path -Parent $scriptDir
$source = Join-Path $repoDir 'skills\twbdoc-ci'

$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }
function T { param([string]$Ja, [string]$En) if ($script:Lang -eq 'en') { return $En }; return $Ja }

if (-not (Test-Path $source)) {
    Write-Host (T "[エラー] スキルが見つかりません: $source" "[Error] Skill not found: $source") -ForegroundColor Red
    exit 2
}
if ($Destination -eq '') {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $Destination = Join-Path $documents 'My Tableau Repository\Tableau Agent\skills'
}
$target = Join-Path $Destination 'twbdoc-ci'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force

# スキルのスクリプトが twbdoc 本体 (この app フォルダ) を見つけられるようにする
$config = @{ twbdoc_app = $scriptDir } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $target 'scripts\config.json'), $config, (New-Object System.Text.UTF8Encoding($false)))

Write-Host (T "[完了] スキルをインストールしました: $target" "[Done] Installed the skill: $target")
Write-Host (T '  Tableau Agent のチャットで /reload-skills を実行してください。' '  Run /reload-skills in the Tableau Agent chat.')
