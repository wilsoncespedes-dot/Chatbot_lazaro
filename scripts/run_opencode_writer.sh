#!/usr/bin/env bash
# Puente del implementer Claude hacia OpenCode/DeepSeek.
# Uso: scripts/run_opencode_writer.sh <feature> [--context progress/review_<feature>.md|progress/impl_<feature>.md]

set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  echo "Uso: $0 <feature> [--context progress/review_<feature>.md|progress/impl_<feature>.md]" >&2
}

if [ "$#" -lt 1 ]; then
  usage
  exit 2
fi

FEATURE="$1"
shift
if [[ ! "$FEATURE" =~ ^[a-z0-9_]+$ ]]; then
  echo "Nombre de feature inválido: usa solo minúsculas, números y guion bajo." >&2
  exit 2
fi

CONTEXT_FILE=""
if [ "$#" -gt 0 ]; then
  if [ "$#" -ne 2 ] || [ "$1" != "--context" ]; then
    usage
    exit 2
  fi
  CONTEXT_FILE="$2"
  case "$CONTEXT_FILE" in
    "progress/review_${FEATURE}.md"|"progress/impl_${FEATURE}.md") ;;
    *) echo "El contexto debe ser el informe de revisión o implementación de esta feature." >&2; exit 2 ;;
  esac
  if [ ! -f "$CONTEXT_FILE" ]; then
    echo "No existe el archivo de contexto: $CONTEXT_FILE" >&2
    exit 2
  fi
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "No encuentro OpenCode. Instálalo antes de delegar la escritura a DeepSeek." >&2
  exit 127
fi

source .claude/hooks/find_python.sh
if [ -z "${PY:-}" ]; then
  echo "No encuentro Python para validar el estado del arnés." >&2
  exit 1
fi

"$PY" - "$FEATURE" <<'PY'
import json
import sys
from pathlib import Path

name = sys.argv[1]
with Path("feature_list.json").open(encoding="utf-8") as source:
    features = json.load(source)["features"]
feature = next((item for item in features if item["name"] == name), None)
if feature is None:
    raise SystemExit(f"La feature {name!r} no está en feature_list.json.")
if feature["status"] != "in_progress":
    raise SystemExit(
        f"La feature {name!r} está {feature['status']!r}; OpenCode solo escribe "
        "una feature aprobada que esté in_progress."
    )
spec = Path("specs") / name
missing = [file for file in ("requirements.md", "design.md", "tasks.md") if not (spec / file).is_file()]
if missing:
    raise SystemExit(f"Faltan archivos de spec para {name}: {', '.join(missing)}")
PY

if ! opencode auth list 2>&1 | grep -Eqi 'OpenCode Go|opencode-go'; then
  echo "No hay credencial OpenCode Go en OpenCode. En la TUI ejecuta /connect, selecciona Other, usa el id 'opencode-go' y pega allí tu API key de OpenCode Go. No la guardes en el repositorio." >&2
  exit 3
fi

MODEL="${OPENCODE_WRITER_MODEL:-opencode-go/deepseek-v4.1-flash}"
PROMPT="Implementa la feature SDD aprobada '${FEATURE}'. Lee y sigue specs/${FEATURE}/requirements.md, design.md y tasks.md en orden. Respeta AGENTS.md y .opencode/agents/implementer.md. No cambies el estado de feature_list.json, no marques done y no edites el harness."
if [ -n "$CONTEXT_FILE" ]; then
  PROMPT+=$'\n\nLee también el informe indicado y atiende sus cambios: '
  PROMPT+="$CONTEXT_FILE"
fi

echo "[harness] Delegando escritura de ${FEATURE} a OpenCode con ${MODEL}."
opencode run --agent implementer --model "$MODEL" "$PROMPT"
