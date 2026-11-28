# 配布用 zip 作成スクリプト (管理者・IT 担当者向け)
#
# 同梱 Python (+ 任意で tableauhyperapi) を含む「そのまま配布できる zip」を作成します。
# 作成した zip を社内のファイルサーバー等に置けば、利用者は展開して
# generate_doc.bat に twbx をドラッグ&ドロップするだけで使えます
# (利用者側でのインストール・ダウンロード・管理者権限は一切不要)。
#
# 版 (-Edition) は 2 種類:
#   Standalone : 単体版。生成 AI を使わず、外部ツールとして動く (既定)。
#                設計書 (generate_doc.bat) と Live CI (live_ci.bat) だけを含む。
#   Agent      : Agent 版 (Tableau Plus 向け)。単体版に加えて、Tableau Agent の
#                スキル (app\skills) とそのインストーラー (install_skill.bat) を含む。
#
# 使い方 (ネットワークに接続できる PC の PowerShell で実行):
#   .\build_distribution.ps1                               # 単体版 (同梱 Python 入り)
#   .\build_distribution.ps1 -Edition Agent                # Agent 版
#   .\build_distribution.ps1 -Edition Agent -WithHyperApi  # + .hyper のサンプル値取得対応
#
# 再配布ライセンス: Python は PSF License、tableauhyperapi は Apache-2.0 のため
# いずれも zip に含めて再配布できます。
param(
    [ValidateSet('Standalone', 'Agent')]
    [string]$Edition = 'Standalone',
    [switch]$WithHyperApi,
    [string]$PythonVersion = '3.14.2',
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$rootDir = Split-Path -Parent $scriptDir

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
# Agent 版だけに入れるもの (パッケージのルートからの相対パス)。
# Tableau Agent 連携のファイルを足したら、ここにも足す。
$AgentOnlyPaths = @(
    'install_skill.bat',
    'app\install_skill.ps1',
    'app\skills'
)
$editionSlug = $Edition.ToLowerInvariant()

if (-not $OutputDir) {
    $OutputDir = Join-Path $rootDir 'dist'
}

# 1. 同梱 Python を準備 (未配置ならダウンロードして配置)
& (Join-Path $scriptDir 'setup_python.ps1') -PythonVersion $PythonVersion -WithHyperApi:$WithHyperApi
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Write-Host (T '[エラー] 同梱 Python の準備に失敗しました。' '[Error] Failed to prepare the bundled Python.') -ForegroundColor Red
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
    # 利用者が使う bat (generate_doc.bat・live_ci.bat・install_skill.bat 等) は
    # 一覧を手で持つと追加時に漏れるため、ルートの *.bat をすべて含める
    # (Agent 版だけのものは、後で $AgentOnlyPaths に従って取り除く)
    $batFiles = @(Get-ChildItem $rootDir -Filter '*.bat' -File)
    if ($batFiles.Count -eq 0) {
        throw (T 'ルートに bat が見つかりません。' 'No .bat files were found in the root folder.')
    }
    foreach ($bat in $batFiles) {
        Copy-Item $bat.FullName $packageRoot
    }
    foreach ($file in @('README.md', 'LICENSE')) {
        Copy-Item (Join-Path $rootDir $file) $packageRoot
    }
    $appDest = Join-Path $packageRoot 'app'
    # app フォルダには twbdoc 本体・起動用 ps1・Tableau Agent スキル (app\skills) が入る
    Copy-Item $scriptDir $appDest -Recurse
    Get-ChildItem $appDest -Recurse -Directory -Filter '__pycache__' |
        Remove-Item -Recurse -Force
    if ($Edition -eq 'Standalone') {
        # 単体版には Tableau Agent 連携 (スキルとインストーラー) を含めない
        foreach ($relative in $AgentOnlyPaths) {
            $target = Join-Path $packageRoot $relative
            if (-not (Test-Path $target)) {
                throw (T "Agent 版だけのファイルが見つかりません: $relative" "Agent-only file not found: $relative")
            }
            Remove-Item $target -Recurse -Force
        }
    }
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
    $zipPath = Join-Path $OutputDir "tableau-workbook-documenter-$version-$editionSlug-$suffix-win64.zip"
    if (Test-Path $zipPath) {
        Remove-Item $zipPath
    }
    Write-Host (T "zip を作成しています: $zipPath" "Creating the zip: $zipPath")
    Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
    Write-Host (T "[完了] $zipPath ($sizeMb MB)" "[Done] $zipPath ($sizeMb MB)") -ForegroundColor Green
    if ($Edition -eq 'Agent') {
        Write-Host (T 'Agent 版です。利用者は展開して generate_doc.bat・live_ci.bat を使い、install_skill.bat で Tableau Agent のスキルを入れます。' 'Agent edition. Users extract it, use generate_doc.bat and live_ci.bat, and run install_skill.bat to add the Tableau Agent skill.')
    } else {
        Write-Host (T '単体版です。利用者は展開して generate_doc.bat (設計書) や live_ci.bat (Live CI) を使うだけです。' 'Standalone edition. Users just extract it and use generate_doc.bat (documentation) or live_ci.bat (Live CI).')
    }
} finally {
    if (Test-Path $stage) {
        Remove-Item -Recurse -Force $stage
    }
}
