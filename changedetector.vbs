' Launch FIT ChangeDetector GUI without showing a console window.
' Uses WScript.Shell with window style 0 (hidden) to suppress cmd.exe.

Dim shell, script_dir, cmd
Set shell = CreateObject("WScript.Shell")

' Get the directory containing this .vbs file (repo root)
script_dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

cmd = "cmd /c """ & _
      "call conda activate Q:\dss_workarea\_contractors\sinorris\conda_environments\changedetector_env" & _
      " && pythonw """ & script_dir & "src\fit_changedetector\gui.py"""""

' Window style 0 = hidden (no console window)
shell.Run cmd, 0, False

Set shell = Nothing