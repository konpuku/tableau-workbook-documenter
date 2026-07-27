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

# 表示言語: TWBDOC_LANG > Windows の表示言語 (Python 側と同じ判定)
$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }

function T {
    param([string]$Ja, [string]$En)
    if ($script:Lang -eq 'en') { return $En }
    return $Ja
}

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
    Write-Host (T '[エラー] Python 3 が見つかりません。' '[Error] Python 3 was not found.') -ForegroundColor Red
    Write-Host (T '  対処方法 (いずれか):' '  How to fix (either):')
    Write-Host (T '  1. 管理者・IT 担当者に「同梱 Python のセットアップ」を依頼する' '  1. Ask your IT administrator to set up the bundled Python')
    Write-Host (T '     (ネットワークに繋がる PC で app\setup_python.ps1 を実行し、フォルダごと配布)' '     (run app\setup_python.ps1 on a PC with internet access, then copy the folder)')
    Write-Host (T '  2. Python をインストールする https://www.python.org/downloads/' '  2. Install Python from https://www.python.org/downloads/')
    Write-Host (T '     (インストール時に "Add python.exe to PATH" にチェック)' '     (check "Add python.exe to PATH" during installation)')
    exit 3
}

if ($python -like '*\python\python.exe') {
    Write-Host (T "同梱の Python を使用します: $python" "Using the bundled Python: $python")
    # 同梱 Python が壊れていないか事前に確認する。
    # 社内のファイル暗号化ソフトが app\python 内のファイルを暗号化すると
    # 「Failed to import encodings module」で起動できなくなるため、
    # 生のエラーを出す代わりに原因と対処方法を案内する。
    $stdlibOk = $false
    try {
        $null = & $python -c 'import encodings' 2>&1
        $stdlibOk = ($LASTEXITCODE -eq 0)
    } catch {
        $stdlibOk = $false
    }
    if (-not $stdlibOk) {
        $pythonDir = Join-Path $scriptDir 'python'
        Write-Host (T '[エラー] 同梱 Python の標準ライブラリを読み込めません。' '[Error] The standard library of the bundled Python cannot be loaded.') -ForegroundColor Red
        Write-Host (T '  ファイル暗号化ソフト (社内の情報漏洩対策ツール等) により、' '  File encryption software (a corporate data-loss-prevention tool, etc.)')
        Write-Host (T '  次のフォルダ内のファイルが変更された可能性があります:' '  may have modified the files in this folder:')
        Write-Host "    $pythonDir"
        Write-Host (T '  対処方法 (いずれか):' '  How to fix (either):')
        Write-Host (T '  1. IT 管理者に、上記フォルダを暗号化・DRM の対象外にするよう相談する' '  1. Ask your IT administrator to exclude the folder above from encryption/DRM')
        Write-Host (T '  2. 配布元の zip を別のフォルダに展開し直してから実行する' '  2. Extract the distribution zip again into a different folder')
        exit 4
    }
}

if (-not $Files -or $Files.Count -eq 0) {
    $searchDirs = @($batDir, (Split-Path -Parent $batDir))
    $targets = @(Get-ChildItem -Path $searchDirs -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.twbx', '.twb' } |
        Select-Object -ExpandProperty FullName)
    if ($targets.Count -eq 0) {
        Write-Host (T '[エラー] 処理対象の .twbx / .twb が見つかりません。' '[Error] No .twbx / .twb files to process were found.') -ForegroundColor Red
        Write-Host (T '  ファイルを generate_doc.bat にドラッグ&ドロップするか、bat と同じフォルダに置いてください。' '  Drag and drop a file onto generate_doc.bat, or put it in the same folder as the bat file.')
        exit 2
    }
    Write-Host (T "引数がないため、フォルダ内の $($targets.Count) ファイルを処理します。" "No arguments given, so $($targets.Count) file(s) in the folder will be processed.")
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
    Write-Host (T '設計書の生成が完了しました。' 'The documentation was generated successfully.') -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host (T '一部または全部の処理に失敗しました。上記のエラーを確認してください。' 'Some or all files failed. Check the errors above.') -ForegroundColor Yellow
}
exit $exitCode
