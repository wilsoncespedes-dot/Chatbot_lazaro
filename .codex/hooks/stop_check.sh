#!/usr/bin/env bash
# Hook Stop: antes de cerrar el turno, fuerza una verificación completa con init.sh
# y te avisa si algo quedó en rojo.

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || true
cat > /dev/null
LOG="${TMPDIR:-${TEMP:-/tmp}}/harness_init.log"

if bash ./init.sh > "$LOG" 2>&1; then
  echo '{"systemMessage": "[harness] init.sh OK"}'
else
  echo "{\"systemMessage\": \"[harness] init.sh FALLÓ — revisa $(echo "$LOG" | sed 's/\\/\\\\/g') antes de cerrar\"}"
fi
exit 0
