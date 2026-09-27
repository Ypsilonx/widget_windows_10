# Vytvoří zástupce ve složce Po spuštění (shell:startup), takže se widget sám
# nastartuje při přihlášení do Windows.
# Zástupce míří přímo na pythonw.exe z .venv (běží bez konzolového okna) – záměrně
# ne přes run_widget.vbs, protože VBScript Windows 11 postupně vypínají.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $scriptDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "Nenalezen $pythonw – nejdřív spusť 'uv sync'."
    exit 1
}

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "ProjectDashboardWidget.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$(Join-Path $scriptDir 'main.py')`""
$shortcut.WorkingDirectory = $scriptDir
$shortcut.IconLocation = Join-Path $scriptDir "assets\icon.ico"
$shortcut.Description = "Project Dashboard Widget"
$shortcut.Save()

Write-Host "Zástupce vytvořen: $shortcutPath"
Write-Host "Pro zrušení automatického startu tento soubor smaž."
