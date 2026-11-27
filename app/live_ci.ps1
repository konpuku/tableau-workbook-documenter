# twbdoc Live CI 起動スクリプト (ワークブックの編集を検査し続ける)
# 通常は 1 つ上のフォルダの live_ci.bat を使ってください。
# 使い方:
#   .\live_ci.ps1                 Tableau Studio に接続できればそれを監視 (保存前の編集も検知)。
#                                 接続できなければ、選んだ保存済みワークブックを監視する
#   .\live_ci.ps1 <file.twbx>     保存済みファイルを監視 (保存するたびに更新)
#   その他のオプションは python -m twbdoc watch --help を参照
#
# 引数は param() で受けず $args をそのまま twbdoc watch に渡す。
# Parameter 属性を付けると高度なスクリプト扱いになり、--out が -OutVariable 等の
# 共通パラメーターと解釈されてエラーになるため。
$WatchArgs = @($args)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path   # app フォルダ
$batDir = Split-Path -Parent $scriptDir                        # live_ci.bat のあるフォルダ

$script:Lang = if ($env:TWBDOC_LANG -match '^(?i)ja') { 'ja' }
    elseif ($env:TWBDOC_LANG -match '^(?i)en') { 'en' }
    elseif ($PSUICulture -like 'ja*') { 'ja' }
    else { 'en' }
function T { param([string]$Ja, [string]$En) if ($script:Lang -eq 'en') { return $En }; return $Ja }

# Python (twbdoc) は UTF-8 で出力するため、日本語の JSON を正しく受け取れるようにする
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

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

# Tableau Studio に接続できるかを twbdoc studio-status で確かめる (接続できれば結果、できなければ $null)
function Get-StudioStatus {
    param([string]$Python)
    $output = & $Python -m twbdoc studio-status --lang $script:Lang 2>$null
    $code = $LASTEXITCODE
    $status = $null
    try { $status = ($output | Out-String) | ConvertFrom-Json } catch { $status = $null }
    return @{ Available = ($code -eq 0); Status = $status }
}

# 監視する保存済みワークブックを選ぶダイアログ (キャンセルなら $null)
function Select-WorkbookFile {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = T '監視するワークブックを選択' 'Choose a workbook to watch'
    $dialog.Filter = (T 'Tableau ワークブック' 'Tableau workbooks') + ' (*.twbx;*.twb)|*.twbx;*.twb'
    $dialog.InitialDirectory = $batDir
    $dialog.Multiselect = $false
    # コンソールや他のウィンドウの後ろに隠れないよう、最前面のフォームを親にする。
    # 親フォームは表示しないと最前面にならないため、画面外に 1px で表示する
    $owner = New-Object System.Windows.Forms.Form
    $owner.TopMost = $true
    $owner.ShowInTaskbar = $false
    $owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $owner.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $owner.Location = New-Object System.Drawing.Point(-32000, -32000)
    $owner.Size = New-Object System.Drawing.Size(1, 1)
    $owner.Show()
    $owner.Activate()
    try {
        if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
            return $dialog.FileName
        }
        return $null
    } finally {
        $owner.Dispose()
        $dialog.Dispose()
    }
}

$python = Find-Python
if ($null -eq $python) {
    Write-Host (T '[エラー] Python 3 が見つかりません。' '[Error] Python 3 was not found.') -ForegroundColor Red
    exit 3
}

Push-Location $scriptDir
try {
    # ワークブックが指定されていなければ (--port 等のオプションだけでも) Studio の状態を確かめる
    $hasWorkbook = @($WatchArgs | Where-Object { "$_" -match '\.twbx?$' }).Count -gt 0
    if (-not $hasWorkbook) {
        $probe = Get-StudioStatus -Python $python
        if ($probe.Available) {
            $title = if ($null -ne $probe.Status) { $probe.Status.workbook } else { '' }
            Write-Host (T "Tableau Studio で開いているワークブックを監視します: $title" "Watching the workbook open in Tableau Studio: $title")
            Write-Host (T '  保存前の編集も数秒で反映されます。' '  Unsaved edits show up within seconds.')
        } else {
            $reason = if ($null -ne $probe.Status -and $probe.Status.reason) { $probe.Status.reason } else { T 'Tableau Studio に接続できません。' 'Cannot connect to Tableau Studio.' }
            Write-Host $reason -ForegroundColor Yellow
            Write-Host (T '保存済みのワークブックを選んで監視します。保存するたびに結果が更新されます。' 'Choose a saved workbook to watch. The results update every time you save it.')
            $file = Select-WorkbookFile
            if ($null -eq $file) {
                Write-Host ''
                Write-Host (T 'ワークブックが選ばれなかったため終了します。使い方:' 'No workbook was chosen, so Live CI will stop. How to use it:')
                Write-Host (T '  - live_ci.bat に .twbx / .twb をドラッグ&ドロップする' '  - Drag and drop a .twbx / .twb file onto live_ci.bat')
                Write-Host (T '  - Tableau Studio (Tableau Plus) では、ヘルプ > 設定とパフォーマンス > External Client API Access をオンにして再起動すると、保存前の編集も監視できます' '  - With Tableau Studio (Tableau Plus), turn on Help > Settings & Performance > External Client API Access and restart Tableau to watch unsaved edits too')
                exit 2
            }
            Write-Host (T "監視するワークブック: $file" "Watching: $file")
            $WatchArgs = @($file) + $WatchArgs
        }
    }
    $arguments = @('-m', 'twbdoc', 'watch', '--open')
    if ($null -ne $WatchArgs) { $arguments += $WatchArgs }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
