' Spustí widget přes pythonw.exe (bez konzolového okna na pozadí).
Set objShell = CreateObject("WScript.Shell")
strPath = objShell.CurrentDirectory
Set objFSO = CreateObject("Scripting.FileSystemObject")
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir
objShell.Run """" & strScriptDir & "\.venv\Scripts\pythonw.exe"" ""main.py""", 0, False
