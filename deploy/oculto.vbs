' Ejecuta un script de Git Bash sin abrir ventana (lo usan las tareas
' programadas de Windows). Uso: wscript oculto.vbs <script.sh> [args...]
Dim shell, args, i, cmd
Set shell = CreateObject("WScript.Shell")
Set args = WScript.Arguments
cmd = """C:\Program Files\Git\bin\bash.exe"" -l"
For i = 0 To args.Count - 1
  cmd = cmd & " """ & args(i) & """"
Next
shell.Run cmd, 0, True
