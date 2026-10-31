#!/usr/bin/env bash
# Hook PostToolUse (Edit|Write): corre los tests y le pasa el resumen a Claude.
# Lo ejecuta Claude Code, no el modelo, así que no se puede saltar.

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || true
cat > /dev/null   # descarta el JSON que Claude Code envía por stdin
source .claude/hooks/find_python.sh

if [ -z "$PY" ]; then
  echo "[harness] No se encontró Python: ejecuta ./init.sh para ver cómo instalarlo."
  exit 0
fi

out=$($PY -m pytest 2>&1); rc=$?
if [ $rc -eq 5 ]; then
  summary="(aún no hay tests)"
else
  summary=$(printf '%s\n' "$out" | tail -3 | tr -d '\r')
fi

printf '%s' "$summary" | $PY -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "[harness] tests tras la edición:\n" + sys.stdin.read().strip(),
    }
}, ensure_ascii=False))
'
exit 0
