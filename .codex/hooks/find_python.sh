# Detector de Python compartido por init.sh, nocturno.sh y los hooks.
# Uso (desde la raíz del repo):  source .claude/hooks/find_python.sh  →  deja $PY
#
# Orden: el .venv del proyecto (Windows o Linux/macOS), luego python3, python y py -3.
# En Windows el `python3` de la Microsoft Store es un acceso directo que no
# ejecuta nada; por eso se prueba que cada candidato funcione de verdad.

export PYTHONUTF8=1

find_python() {
  local c
  for c in ".venv/Scripts/python.exe" ".venv/bin/python" python3 python "py -3"; do
    case "$c" in
      .venv/*) [ -x "$c" ] || continue ;;
    esac
    if $c -c "import sys" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

PY="$(find_python || true)"
