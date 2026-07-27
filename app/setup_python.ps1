# 同梱 Python のセットアップスクリプト (管理者・IT 担当者向け / 実行は 1 回だけ)
#
# ネットワークに接続できる PC で実行すると、python.org から Windows embeddable 版
# Python (約 11MB、インストール不要) をダウンロードして app\python に配置します。
# 完了後、ツールのフォルダごとコピー・配布すれば、Python 未導入の PC でも動作します。
#
# 使い方 (PowerShell で実行):
#   .\setup_python.ps1                  # Python 本体のみ
#   .\setup_python.ps1 -WithHyperApi    # + Tableau 抽出 (.hyper) のサンプル値取得対応
#                                       #   (実行する PC に pip 付きの Python が必要。約 +225MB)
param(
    [string]$PythonVersion = '3.14.2',
    [switch]$WithHyperApi,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDir = Join-Path $scriptDir 'python'

# 表示言語: TWBDOC_LANG > Windows の表示言語
$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }

function T {
    param([string]$Ja, [string]$En)
    if ($script:Lang -eq 'en') { return $En }
    return $Ja
}

if ((Test-Path $pythonDir) -and -not $Force) {
    Write-Host (T "[スキップ] $pythonDir は既に存在します。作り直す場合は -Force を付けてください。" "[Skipped] $pythonDir already exists. Use -Force to recreate it.")
} else {
    if (Test-Path $pythonDir) {
        Remove-Item -Recurse -Force $pythonDir
    }
    $zipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    $zipPath = Join-Path $env:TEMP "python-$PythonVersion-embed-amd64.zip"
    Write-Host (T "Python embeddable 版をダウンロードしています: $zipUrl" "Downloading the Python embeddable package: $zipUrl")
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Write-Host (T "展開しています: $pythonDir" "Extracting to: $pythonDir")
    Expand-Archive -Path $zipPath -DestinationPath $pythonDir
    Remove-Item $zipPath

    Write-Host (T "[完了] 同梱 Python を配置しました: $pythonDir" "[Done] The bundled Python is ready: $pythonDir") -ForegroundColor Green
}

# 標準ライブラリを zip から展開する (社内のファイル暗号化ソフト対策)
#   embeddable 版は標準ライブラリを pythonXXX.zip 1 個にまとめているが、
#   .zip を暗号化する社内ツールがある環境では Python が起動できなくなる
#   (Fatal Python error: Failed to import encodings module)。
#   Lib フォルダへ展開して zip を削除することでこれを回避する。
$stdlibZip = Get-ChildItem -Path $pythonDir -Filter 'python*.zip' | Select-Object -First 1
if ($null -ne $stdlibZip) {
    Write-Host (T '標準ライブラリを展開しています (ファイル暗号化ソフト対策)...' 'Extracting the standard library (workaround for file encryption software)...')
    Expand-Archive -Path $stdlibZip.FullName -DestinationPath (Join-Path $pythonDir 'Lib') -Force
    Remove-Item $stdlibZip.FullName
    Write-Host (T '[完了] 標準ライブラリを Lib フォルダへ展開しました (.zip は削除)。' '[Done] The standard library was extracted into the Lib folder (.zip removed).') -ForegroundColor Green
}

# ._pth を書き換えて標準ライブラリ (Lib) と twbdoc (app フォルダ) を import 可能にする
$pthFile = Get-ChildItem -Path $pythonDir -Filter 'python*._pth' | Select-Object -First 1
if ($null -eq $pthFile) {
    Write-Host (T '[エラー] ._pth ファイルが見つかりません。' '[Error] The ._pth file was not found.') -ForegroundColor Red
    exit 1
}
@(
    'Lib'
    '.'
    'Lib\site-packages'
    '..'
) | Set-Content -Path $pthFile.FullName -Encoding ascii

if ($WithHyperApi) {
    $sitePackages = Join-Path $pythonDir 'Lib\site-packages'
    if (Test-Path (Join-Path $sitePackages 'tableauhyperapi')) {
        Write-Host (T '[スキップ] tableauhyperapi は導入済みです。' '[Skipped] tableauhyperapi is already installed.')
    } else {
        $pip = $null
        foreach ($candidate in @('py', 'python')) {
            $command = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($null -ne $command) {
                try {
                    & $candidate -m pip --version *> $null
                    if ($LASTEXITCODE -eq 0) { $pip = $candidate; break }
                } catch { continue }
            }
        }
        if ($null -eq $pip) {
            Write-Host (T '[エラー] pip 付きの Python が見つかりません。' '[Error] No Python with pip was found.') -ForegroundColor Red
            Write-Host (T '  -WithHyperApi の実行には、この PC に通常版の Python が必要です。' '  -WithHyperApi requires a regular Python installation on this PC.')
            exit 1
        }
        Write-Host (T 'tableauhyperapi をダウンロードしています (約 225MB)...' 'Downloading tableauhyperapi (about 225MB)...')
        & $pip -m pip install tableauhyperapi --target $sitePackages --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host (T '[エラー] tableauhyperapi の導入に失敗しました。' '[Error] Failed to install tableauhyperapi.') -ForegroundColor Red
            exit 1
        }
        Write-Host (T '[完了] tableauhyperapi を同梱しました (.hyper のサンプル値取得が有効になります)。' '[Done] tableauhyperapi is bundled (sample values can be read from .hyper extracts).') -ForegroundColor Green
    }
}

# 暗号化対象になりやすい .txt を配布物から一掃する (ライセンス・メタ情報で実行には不要)
#   社内のファイル暗号化ソフトが .txt を暗号化しても Python の動作に影響しないよう、
#   拡張子を .dat に変更して中身はそのまま残す。
$renamedCount = 0
foreach ($textFile in Get-ChildItem -Path $pythonDir -Recurse -File -Filter '*.txt') {
    $target = [IO.Path]::ChangeExtension($textFile.FullName, '.dat')
    if (-not (Test-Path $target)) {
        Rename-Item -Path $textFile.FullName -NewName ([IO.Path]::GetFileName($target))
        $renamedCount++
    }
}
if ($renamedCount -gt 0) {
    Write-Host (T "[完了] .txt $renamedCount 件を .dat にリネームしました (ファイル暗号化ソフト対策)。" "[Done] Renamed $renamedCount .txt file(s) to .dat (workaround for file encryption software).") -ForegroundColor Green
}

Write-Host ''
Write-Host (T 'このフォルダ (ツール一式) をコピーして配布してください。配布先で追加のインストールは不要です。' 'Copy this folder to distribute the tool. No additional installation is needed on the target PC.')
