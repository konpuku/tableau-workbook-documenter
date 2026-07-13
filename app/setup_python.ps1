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

if ((Test-Path $pythonDir) -and -not $Force) {
    Write-Host "[スキップ] $pythonDir は既に存在します。作り直す場合は -Force を付けてください。"
} else {
    if (Test-Path $pythonDir) {
        Remove-Item -Recurse -Force $pythonDir
    }
    $zipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    $zipPath = Join-Path $env:TEMP "python-$PythonVersion-embed-amd64.zip"
    Write-Host "Python embeddable 版をダウンロードしています: $zipUrl"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Write-Host "展開しています: $pythonDir"
    Expand-Archive -Path $zipPath -DestinationPath $pythonDir
    Remove-Item $zipPath

    # ._pth を書き換えて twbdoc (app フォルダ) と site-packages を import 可能にする
    $pthFile = Get-ChildItem -Path $pythonDir -Filter 'python*._pth' | Select-Object -First 1
    if ($null -eq $pthFile) {
        Write-Host '[エラー] ._pth ファイルが見つかりません。' -ForegroundColor Red
        exit 1
    }
    $zipName = (Get-ChildItem -Path $pythonDir -Filter 'python*.zip' | Select-Object -First 1).Name
    @(
        $zipName
        '.'
        'Lib\site-packages'
        '..'
    ) | Set-Content -Path $pthFile.FullName -Encoding ascii
    Write-Host "[完了] 同梱 Python を配置しました: $pythonDir" -ForegroundColor Green
}

if ($WithHyperApi) {
    $sitePackages = Join-Path $pythonDir 'Lib\site-packages'
    if (Test-Path (Join-Path $sitePackages 'tableauhyperapi')) {
        Write-Host '[スキップ] tableauhyperapi は導入済みです。'
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
            Write-Host '[エラー] pip 付きの Python が見つかりません。' -ForegroundColor Red
            Write-Host '  -WithHyperApi の実行には、この PC に通常版の Python が必要です。'
            exit 1
        }
        Write-Host 'tableauhyperapi をダウンロードしています (約 225MB)...'
        & $pip -m pip install tableauhyperapi --target $sitePackages --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[エラー] tableauhyperapi の導入に失敗しました。' -ForegroundColor Red
            exit 1
        }
        Write-Host '[完了] tableauhyperapi を同梱しました (.hyper のサンプル値取得が有効になります)。' -ForegroundColor Green
    }
}

Write-Host ''
Write-Host 'このフォルダ (ツール一式) をコピーして配布してください。配布先で追加のインストールは不要です。'
