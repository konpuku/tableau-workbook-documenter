# 配布用 zip 作成スクリプト (管理者・IT 担当者向け)
#
# 同梱 Python (+ 任意で tableauhyperapi) を含む「そのまま配布できる zip」を作成します。
# 作成した zip を社内のファイルサーバー等に置けば、利用者は展開して
# generate_doc.bat に twbx をドラッグ&ドロップするだけで使えます
# (利用者側でのインストール・ダウンロード・管理者権限は一切不要)。
#
# 使い方 (ネットワークに接続できる PC の PowerShell で実行):
#   .\build_distribution.ps1                  # 同梱 Python 入り zip
#   .\build_distribution.ps1 -WithHyperApi    # + .hyper のサンプル値取得対応 zip
#
# 再配布ライセンス: Python は PSF License、tableauhyperapi は Apache-2.0 のため
# いずれも zip に含めて再配布できます。
param(
    [switch]$WithHyperApi,
    [string]$PythonVersion = '3.14.2',
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$rootDir = Split-Path -Parent $scriptDir
if (-not $OutputDir) {
    $OutputDir = Join-Path $rootDir 'dist'
}

# 1. 同梱 Python を準備 (未配置ならダウンロードして配置)
& (Join-Path $scriptDir 'setup_python.ps1') -PythonVersion $PythonVersion -WithHyperApi:$WithHyperApi
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Write-Host '[エラー] 同梱 Python の準備に失敗しました。' -ForegroundColor Red
    exit 1
}

# 2. バージョン取得
$initContent = Get-Content (Join-Path $scriptDir 'twbdoc\__init__.py') -Raw
$version = if ($initContent -match '__version__\s*=\s*"([^"]+)"') { "v$($Matches[1])" } else { 'dev' }

# 3. ステージング (配布に不要なものを除いてコピー)
$stage = Join-Path $env:TEMP "twbdoc_dist_$([guid]::NewGuid().ToString('N'))"
$packageRoot = Join-Path $stage 'tableau-workbook-documenter'
New-Item -ItemType Directory -Force $packageRoot | Out-Null
try {
    foreach ($file in @('generate_doc.bat', 'README.md', 'LICENSE')) {
        Copy-Item (Join-Path $rootDir $file) $packageRoot
    }
    $appDest = Join-Path $packageRoot 'app'
    Copy-Item $scriptDir $appDest -Recurse
    Get-ChildItem $appDest -Recurse -Directory -Filter '__pycache__' |
        Remove-Item -Recurse -Force
    if (-not $WithHyperApi) {
        # hyper なし版には tableauhyperapi を含めない (サイズ削減)
        $sitePackages = Join-Path $appDest 'python\Lib\site-packages'
        if (Test-Path $sitePackages) {
            Get-ChildItem $sitePackages -Filter 'tableauhyperapi*' |
                Remove-Item -Recurse -Force
        }
    }

    # 4. zip 化
    $suffix = if ($WithHyperApi) { 'with-python-hyperapi' } else { 'with-python' }
    New-Item -ItemType Directory -Force $OutputDir | Out-Null
    $zipPath = Join-Path $OutputDir "tableau-workbook-documenter-$version-$suffix-win64.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath
    }
    Write-Host "zip を作成しています: $zipPath"
    Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
    Write-Host "[完了] $zipPath ($sizeMb MB)" -ForegroundColor Green
    Write-Host 'この zip を配布してください。利用者は展開して generate_doc.bat を使うだけです。'
} finally {
    if (Test-Path $stage) {
        Remove-Item -Recurse -Force $stage
    }
}
