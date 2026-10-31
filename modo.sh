#!/usr/bin/env bash
# modo.sh — Cambia el arnés entre modo SUPERVISADO y modo NOCTURNO.
#
#   ./modo.sh                 muestra el modo actual
#   ./modo.sh supervisado     tú apruebas los specs y los comandos dudosos
#   ./modo.sh nocturno        autónomo: no pregunta nada, no para en spec_ready
#   ./modo.sh --actual        imprime solo el nombre del modo (para scripts)
#
# Copia .claude/modes/<modo>.json sobre .claude/settings.json. Claude Code lee
# la configuración al arrancar, así que reinícialo después de cambiar de modo.

set -u
cd "$(dirname "$0")"

MODES_DIR=".claude/modes"
CONF=".claude/settings.json"

current_mode() {
  for m in supervisado nocturno; do
    if [ -f "$CONF" ] && [ "$(tr -d '\r' < "$CONF")" = "$(tr -d '\r' < "$MODES_DIR/$m.json")" ]; then
      echo "$m"
      return
    fi
  done
  echo "personalizado"
}

describe() {
  case "$1" in
    supervisado)
      echo "  · El leader se detiene en spec_ready hasta que digas «aprobado»."
      echo "  · Todo permitido; solo pregunta antes de lo arriesgado (git push, rm -rf, borrar volúmenes…)."
      ;;
    nocturno)
      echo "  · El leader sigue .claude/nocturno.md: el reviewer aprueba los specs por ti."
      echo "  · No pide permisos (dontAsk): todo permitido salvo lo arriesgado, que se deniega."
      echo "  · Para trabajar toda la noche usa ./nocturno.sh"
      ;;
    *)
      echo "  · .claude/settings.json fue editado a mano y no coincide con ningún modo."
      ;;
  esac
}

case "${1:-}" in
  "")
    m=$(current_mode)
    echo "Modo actual: $m"
    describe "$m"
    ;;
  --actual)
    current_mode
    ;;
  supervisado|nocturno)
    target="$1"
    quiet="${2:-}"
    if [ ! -f "$MODES_DIR/$target.json" ]; then
      echo "Falta $MODES_DIR/$target.json" >&2
      exit 1
    fi
    if [ "$(current_mode)" = "personalizado" ] && [ -f "$CONF" ]; then
      cp "$CONF" "$CONF.bak"
      [ "$quiet" = "--quiet" ] || echo "$CONF tenía cambios propios: copia guardada en $CONF.bak"
    fi
    cp "$MODES_DIR/$target.json" "$CONF"
    if [ "$quiet" != "--quiet" ]; then
      echo "Modo cambiado a: $target"
      describe "$target"
      echo "Reinicia Claude Code para que el cambio tenga efecto."
    fi
    ;;
  *)
    echo "Uso: ./modo.sh [supervisado|nocturno|--actual]" >&2
    exit 2
    ;;
esac
