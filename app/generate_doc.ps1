# Tableau ワークブック設計書生成ツール 起動スクリプト
# 通常はこのファイルを直接実行せず、1 つ上のフォルダの generate_doc.bat を使ってください。
# 使い方:
#   .\generate_doc.ps1 <file1.twbx> [<file2.twb> ...]
#   引数なしの場合は bat のあるフォルダとその親フォルダの *.twbx / *.twb を全て処理する
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Files
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$batDir = Split-Path -Parent $scriptDir                        # generate_doc.bat のあるフォルダ

function Find-Python {
    # 同梱の Python (app\python) があれば最優先で使う
    $bundled = Join-Path $scriptDir 'python\python.exe'
    if (Test-Path $bundled) {
        return $bundled
    }
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
    Write-Host '  対処方法 (いずれか):'
    Write-Host '  1. 管理者・IT 担当者に「同梱 Python のセットアップ」を依頼する'
    Write-Host '     (ネットワークに繋がる PC で app\setup_python.ps1 を実行し、フォルダごと配布)'
    Write-Host '  2. Python をインストールする https://www.python.org/downloads/'
    Write-Host '     (インストール時に "Add python.exe to PATH" にチェック)'
    exit 3
}

if ($python -like '*\python\python.exe') {
    Write-Host "同梱の Python を使用します: $python"
}

if (-not $Files -or $Files.Count -eq 0) {
    $searchDirs = @($batDir, (Split-Path -Parent $batDir))
    $targets = @(Get-ChildItem -Path $searchDirs -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.twbx', '.twb' } |
        Select-Object -ExpandProperty FullName)
    if ($targets.Count -eq 0) {
        Write-Host '[エラー] 処理対象の .twbx / .twb が見つかりません。' -ForegroundColor Red
        Write-Host '  ファイルを generate_doc.bat にドラッグ&ドロップするか、bat と同じフォルダに置いてください。'
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
