# Tableau ワークブック設計書生成ツール 起動スクリプト
# 使い方:
#   .\generate_doc.ps1 <file1.twbx> [<file2.twb> ...]
#   引数なしの場合はこのフォルダと親フォルダの *.twbx / *.twb を全て処理する
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Files
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    foreach ($candidate in @('py', 'python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            try {
                $version = & $candidate --version 2>&1
                if ("$version" -match 'Python 3') {
                    return $candidate
                }
            } catch {
                continue
            }
        }
    }
    return $null
}

$python = Find-Python
if ($null -eq $python) {
    Write-Host '[エラー] Python 3 が見つかりません。' -ForegroundColor Red
    Write-Host '  会社の PC の場合はソフトウェアセンター等から Python をインストールしてください。'
    Write-Host '  https://www.python.org/downloads/ (インストール時に "Add python.exe to PATH" にチェック)'
    exit 3
}

if (-not $Files -or $Files.Count -eq 0) {
    $targets = @(Get-ChildItem -Path $scriptDir, (Split-Path -Parent $scriptDir) -File |
        Where-Object { $_.Extension -in '.twbx', '.twb' } |
        Select-Object -ExpandProperty FullName)
    if ($targets.Count -eq 0) {
        Write-Host '[エラー] 処理対象の .twbx / .twb が見つかりません。' -ForegroundColor Red
        Write-Host '  ファイルをこの bat にドラッグ&ドロップするか、twbx と同じフォルダに置いてください。'
        exit 2
    }
    Write-Host "引数がないため、フォルダ内の $($targets.Count) ファイルを処理します。"
} else {
    $targets = $Files
}

$env:PYTHONIOENCODING = 'utf-8'
# どのフォルダから起動しても twbdoc パッケージを見つけられるようにする (既存値は保持)
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$scriptDir;$env:PYTHONPATH" } else { $scriptDir }
& $python -m twbdoc @targets
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host ''
    Write-Host '設計書の生成が完了しました。' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host '一部または全部の処理に失敗しました。上記のエラーを確認してください。' -ForegroundColor Yellow
}
exit $exitCode
