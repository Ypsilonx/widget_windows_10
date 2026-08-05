# Vytvoří zástupce na run_widget.vbs ve složce Po spuštění (shell:startup),
# takže se widget sám nastartuje při přihlášení do Windows.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "ProjectDashboardWidget.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $scriptDir "run_widget.vbs"
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "Project Dashboard Widget"
$shortcut.Save()

Write-Host "Zástupce vytvořen: $shortcutPath"
Write-Host "Pro zrušení automatického startu tento soubor smaž."
