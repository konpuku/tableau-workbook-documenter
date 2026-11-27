# twbdoc Live CI 起動スクリプト (Tableau Studio の編集をリアルタイムに検査)
# 通常は 1 つ上のフォルダの live_ci.bat を使ってください。
# 使い方:
#   .\live_ci.ps1                 Tableau Studio で開いているワークブックを監視
#   .\live_ci.ps1 <file.twbx>     保存済みファイルを監視
#   その他のオプションは python -m twbdoc watch --help を参照
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$WatchArgs
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ

$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }
function T { param([string]$Ja, [string]$En) if ($script:Lang -eq 'en') { return $En }; return $Ja }

function Find-Python {
    $bundled = Join-Path $scriptDir 'python\python.exe'
    if (Test-Path $bundled) { return $bundled }
    foreach ($candidate in @('py', 'python')) {
        if ($null -ne (Get-Command $candidate -ErrorAction SilentlyContinue)) {
            try {
                $version = & $candidate --version 2>&1
                if ("$version" -match 'Python 3') { return $candidate }
            } catch { continue }
        }
    }
    return $null
}

$python = Find-Python
if ($null -eq $python) {
    Write-Host (T '[エラー] Python 3 が見つかりません。' '[Error] Python 3 was not found.') -ForegroundColor Red
    exit 3
}

Push-Location $scriptDir
try {
    $arguments = @('-m', 'twbdoc', 'watch', '--open')
    if ($null -ne $WatchArgs) { $arguments += $WatchArgs }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
