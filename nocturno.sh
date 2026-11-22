#!/usr/bin/env bash
# nocturno.sh — Trabajo autónomo 24/7: procesa features una tras otra sin
# preguntarte nada, hasta que no quede trabajo o salte un freno de seguridad.
#
#   ./nocturno.sh [opciones]
#
#   --max-sesiones N   máximo de sesiones de Claude Code (0 = sin límite)
#   --max-horas H      parar tras H horas (0 = sin límite)
#   --timeout-min M    máximo de minutos por sesión (0 = sin límite)
#   --modelo M         modelo de Claude leader, p. ej. sonnet u opus
#   --sin-commits      no hacer un commit de git después de cada sesión
#
# Cada sesión lanza `claude -p` con las instrucciones de .claude/nocturno.md
# y --permission-mode dontAsk (deniega en vez de preguntar). Lleva UNA
# feature hasta done o blocked. Al terminar (o con Ctrl+C) el arnés vuelve
# al modo en el que estaba.
#
# Se detiene si:
#   · no quedan features pending / spec_ready / in_progress
#   · se alcanza un límite explícito (--max-sesiones o --max-horas)
# Si una sesión no avanza o falla la verificación, reintenta con espera creciente.

set -u
cd "$(dirname "$0")"

# Claude Code cancela sus tareas en segundo plano tras 10 minutos por defecto.
# El modo autónomo debe esperar al writer antes de verificar o relanzar la feature.
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0

# Evita que el ordenador se duerma mientras trabaja (macOS / Linux con systemd).
if [ -z "${NOCTURNO_DESPIERTO:-}" ]; then
  export NOCTURNO_DESPIERTO=1
  if command -v caffeinate >/dev/null 2>&1; then
    exec caffeinate -ims "$0" "$@"
  elif command -v systemd-inhibit >/dev/null 2>&1 && systemd-inhibit --what=idle true >/dev/null 2>&1; then
    exec systemd-inhibit --what=idle:sleep --why="nocturno.sh trabajando" "$0" "$@"
  else
    echo "[nocturno] [WARN] No se detectó inhibidor de suspensión; mantén el equipo despierto durante la ejecución."
  fi
fi

MAX_SESIONES=0
MAX_HORAS=0
TIMEOUT_MIN=0
MODELO=""
COMMIT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --max-sesiones) MAX_SESIONES="$2"; shift 2 ;;
    --max-horas)    MAX_HORAS="$2"; shift 2 ;;
    --timeout-min)  TIMEOUT_MIN="$2"; shift 2 ;;
    --modelo)       MODELO="$2"; shift 2 ;;
    --sin-commits)  COMMIT=0; shift ;;
    -h|--help)      sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1 (usa --help)" >&2; exit 2 ;;
  esac
done

for limite in "$MAX_SESIONES" "$MAX_HORAS" "$TIMEOUT_MIN"; do
  if ! [[ "$limite" =~ ^(0|[1-9][0-9]*)$ ]]; then
    echo "[nocturno] Los límites deben ser enteros no negativos (0 = sin límite)." >&2
    exit 2
  fi
done

# ── Requisitos ────────────────────────────────────────────────────────────
source .claude/hooks/find_python.sh
if [ -z "$PY" ]; then
  echo "[nocturno] No encuentro Python. Ejecuta ./init.sh para ver cómo arreglarlo." >&2
  exit 1
fi

# El instalador nativo de Claude Code deja el programa en ~/.local/bin, que a
# veces no está en el PATH (sobre todo en Windows/Git Bash).
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac

if ! command -v claude >/dev/null 2>&1; then
  echo "[nocturno] No encuentro el comando 'claude'. Instala Claude Code primero." >&2
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "[nocturno] No encuentro 'opencode'. Es necesario porque DeepSeek es el writer." >&2
  exit 1
fi

source .claude/hooks/opencode_writer.sh

MODEL_FLAG=""
[ -n "$MODELO" ] && MODEL_FLAG="--model $MODELO"

TIMEOUT_BIN=""
TIMEOUT_SECONDS=""
if [ "$TIMEOUT_MIN" -gt 0 ]; then
  if command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN="gtimeout"
    TIMEOUT_SECONDS="$((TIMEOUT_MIN * 60))"
  elif command -v timeout >/dev/null 2>&1 && timeout --version 2>&1 | grep -q "GNU coreutils"; then
    TIMEOUT_BIN="timeout"
    TIMEOUT_SECONDS="$((TIMEOUT_MIN * 60))"
  else
    echo "[nocturno] [WARN] No se encontró GNU timeout; las sesiones no tendrán límite automático de duración."
  fi
fi

run_claude() {
  if [ -n "$TIMEOUT_BIN" ]; then
    "$TIMEOUT_BIN" "$TIMEOUT_SECONDS" claude "$@"
  else
    claude "$@"
  fi
}

USE_GIT=0
if [ "$COMMIT" = "1" ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  USE_GIT=1
  if [ -n "$(git status --porcelain)" ]; then
    echo "[nocturno] Tienes cambios sin commitear. Haz commit o stash antes de" >&2
    echo "           dejarlo solo, o lánzalo con --sin-commits." >&2
    exit 1
  fi
fi

# ── Helpers ───────────────────────────────────────────────────────────────
next_feature() {
  $PY - <<'PY'
import json
fs = json.load(open("feature_list.json", encoding="utf-8"))["features"]
by_id = {str(f["id"]): f for f in fs}
for wanted in ("in_progress", "spec_ready", "pending"):
    for f in sorted(fs, key=lambda f: f["id"]):
        deps = f.get("dependencies", [])
        deps_done = all(
            str(dep) in by_id and by_id[str(dep)].get("status", "done") == "done"
            for dep in deps
        )
        if f["status"] == wanted and deps_done:
            print(f'{f["id"]}\t{f["name"]}\t{f["status"]}')
            raise SystemExit
PY
}

status_of() {
  $PY - "$1" <<'PY'
import json, sys
fs = json.load(open("feature_list.json", encoding="utf-8"))["features"]
print(next((f["status"] for f in fs if str(f["id"]) == sys.argv[1]), "?"))
PY
}

reopen_done_feature() {
  $PY - "$1" <<'PY'
import json
import re
import sys
from pathlib import Path

target = sys.argv[1]
path = Path("feature_list.json")
text = path.read_text(encoding="utf-8")
features = json.loads(text)["features"]
feature = next((f for f in features if str(f["id"]) == target), None)
if feature is None or feature["status"] != "done":
    raise SystemExit(0)

match = re.search(r'"features"\s*:\s*\[', text)
if match is None:
    raise SystemExit("No se encuentra el arreglo features en feature_list.json.")
decoder = json.JSONDecoder()
cursor = match.end()
while cursor < len(text):
    while cursor < len(text) and (text[cursor].isspace() or text[cursor] == ","):
        cursor += 1
    if cursor >= len(text) or text[cursor] == "]":
        break
    start = cursor
    item, cursor = decoder.raw_decode(text, cursor)
    if str(item.get("id")) != target:
        continue
    updated, count = re.subn(
        r'("status"\s*:\s*)"done"', r'\1"in_progress"', text[start:cursor], count=1
    )
    if count != 1:
        raise SystemExit(f"No se pudo reabrir la feature #{target}.")
    path.write_text(text[:start] + updated + text[cursor:], encoding="utf-8")
    break
else:
    raise SystemExit(f"No se pudo localizar la feature #{target} en feature_list.json.")
PY
}

snapshot() { $PY -c 'import json;print(json.dumps([(f["id"],f["status"]) for f in json.load(open("feature_list.json",encoding="utf-8"))["features"]]))'; }

if [ -n "$(next_feature)" ] && ! opencode_writer_authenticated; then
  echo "[nocturno] Hay trabajo pendiente, pero OpenCode Go no está conectado. Ejecuta /connect, selecciona Other y configura el proveedor 'opencode-go'." >&2
  exit 1
fi

now() { date "+%Y-%m-%d %H:%M"; }

# ── Preparación ───────────────────────────────────────────────────────────
mkdir -p progress
REPORT="progress/nocturno_$(date +%Y-%m-%d_%H%M).md"
LOG="progress/nocturno.log"
PREV_MODE=$(bash ./modo.sh --actual)
restore_mode() {
  if [ "$PREV_MODE" = "supervisado" ] || [ "$PREV_MODE" = "nocturno" ]; then
    bash ./modo.sh "$PREV_MODE" --quiet
  elif [ -f .claude/settings.json.bak ]; then
    cp .claude/settings.json.bak .claude/settings.json
  fi
}
trap 'restore_mode' EXIT
trap 'echo; echo "[nocturno] Interrumpido por el usuario."; echo "- $(now) — interrumpido manualmente" >> "$REPORT"; exit 130' INT TERM

bash ./modo.sh nocturno --quiet
START=$(date +%s)

{
  echo "# Informe nocturno — $(now)"
  echo
  echo "Límites: $MAX_SESIONES sesiones, $MAX_HORAS h, $TIMEOUT_MIN min/sesión (0 = sin límite). Commits: $([ $USE_GIT = 1 ] && echo sí || echo no)."
  echo
  echo "## Sesiones"
  echo
} > "$REPORT"

echo "[nocturno] Comprobando el entorno con ./init.sh..."
if ! bash ./init.sh > /dev/null 2>&1; then
  echo "- $(now) — init.sh en rojo antes de la primera sesión; se inicia recuperación sobre la feature accionable." >> "$REPORT"
  echo "[nocturno] init.sh está en rojo; Claude retomará la feature y corregirá antes de cerrarla." >&2
fi

# ── Bucle principal ───────────────────────────────────────────────────────
sesion=0
sin_cambios=0
retry_wait=30
motivo="sin trabajo pendiente"

while :; do
  next=$(next_feature)
  if [ -z "$next" ]; then motivo="no quedan features pendientes"; break; fi
  if [ "$MAX_SESIONES" -gt 0 ] && [ "$sesion" -ge "$MAX_SESIONES" ]; then motivo="alcanzado --max-sesiones ($MAX_SESIONES)"; break; fi
  if [ "$MAX_HORAS" -gt 0 ] && [ $(( $(date +%s) - START )) -ge $(( MAX_HORAS * 3600 )) ]; then motivo="alcanzado --max-horas ($MAX_HORAS)"; break; fi

  IFS=$'\t' read -r fid fname fstatus <<< "${next//$'\r'/}"
  sesion=$((sesion + 1))
  echo "[nocturno] $(now) — sesión $sesion: feature #$fid $fname ($fstatus)"

  before=$(snapshot)
  {
    echo
    echo "════════ $(now) — sesión $sesion — #$fid $fname ($fstatus) ════════"
  } >> "$LOG"
  run_claude -p \
    "MODO NOCTURNO. Procesa la siguiente feature (#$fid $fname) siguiendo .claude/nocturno.md y termina." \
    --append-system-prompt-file .claude/nocturno.md \
    --permission-mode dontAsk $MODEL_FLAG \
    >> "$LOG" 2>&1 < /dev/null
  rc=$?
  after=$(snapshot)
  nuevo=$(status_of "$fid" | tr -d '\r')

  if bash ./init.sh > /dev/null 2>&1; then init_ok=1; init_txt="verde"; else init_ok=0; init_txt="ROJO"; fi
  if [ "$init_ok" = "0" ] && [ "$nuevo" = "done" ]; then
    reopen_done_feature "$fid"
    nuevo=$(status_of "$fid" | tr -d '\r')
    after=$(snapshot)
  fi
  [ "$rc" = "124" ] && extra=" (timeout)" || extra=""
  echo "- $(now) — #$fid \`$fname\`: $fstatus → **$nuevo** · init.sh $init_txt · exit $rc$extra" >> "$REPORT"
  echo "[nocturno]   → $nuevo, init.sh $init_txt"

  if [ "$USE_GIT" = "1" ] && [ -n "$(git status --porcelain)" ]; then
    git add -A -- . ":(exclude).claude/settings.json" ":(exclude).claude/settings.json.bak" && git commit -q -m "nocturno: #$fid $fname → $nuevo" || true
  fi

  if [ "$before" = "$after" ] || [ "$init_ok" = "0" ]; then
    sin_cambios=$((sin_cambios + 1))
    echo "[nocturno]   Sin avance verificable; reintento en ${retry_wait}s (intento ${sin_cambios})."
    sleep "$retry_wait"
    retry_wait=$((retry_wait * 2))
    [ "$retry_wait" -gt 1800 ] && retry_wait=1800
  else
    sin_cambios=0
    retry_wait=30
  fi
done

# ── Resumen para la mañana ────────────────────────────────────────────────
$PY - "$REPORT" "$motivo" "$sesion" <<'PY'
import json, sys
report, motivo, sesiones = sys.argv[1], sys.argv[2], sys.argv[3]
fs = json.load(open("feature_list.json", encoding="utf-8"))["features"]
auto = [f for f in fs if f.get("auto_approved")]
blocked = [f for f in fs if f["status"] == "blocked"]
pend = [f for f in fs if f["status"] in ("pending", "spec_ready", "in_progress")]
with open(report, "a", encoding="utf-8") as out:
    out.write(f"\n## Fin\n\nMotivo de parada: **{motivo}** ({sesiones} sesiones).\n")
    out.write("\n## Qué revisar por la mañana\n\n")
    if auto:
        out.write("Specs aprobados por el reviewer, no por ti (léelos):\n")
        for f in auto:
            out.write(f"- #{f['id']} `{f['name']}` ({f['status']}) → `specs/{f['name']}/` "
                      f"y `progress/specreview_{f['name']}.md`\n")
    if blocked:
        out.write("\nFeatures bloqueadas que necesitan una decisión tuya:\n")
        for f in blocked:
            out.write(f"- #{f['id']} `{f['name']}` → `progress/blocked_{f['name']}.md`\n")
    if pend:
        out.write("\nTodavía pendientes: " + ", ".join(f"#{f['id']} `{f['name']}`" for f in pend) + "\n")
    if not (auto or blocked or pend):
        out.write("Nada: todo está `done` y no hay specs auto-aprobados.\n")
    out.write("\nLog completo de Claude Code: `progress/nocturno.log`\n")
PY

if [ "$USE_GIT" = "1" ] && [ -n "$(git status --porcelain -- progress)" ]; then
  git add -A -- progress && git commit -q -m "nocturno: informe $(basename "$REPORT")" || true
fi

echo "[nocturno] Fin: $motivo. Informe en $REPORT"
