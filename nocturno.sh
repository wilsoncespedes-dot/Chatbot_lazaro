#!/usr/bin/env bash
# nocturno.sh — Trabajo autónomo 24/7: procesa features una tras otra sin
# preguntarte nada, hasta que no quede trabajo o salte un freno de seguridad.
#
#   ./nocturno.sh [opciones]
#
#   --max-sesiones N   máximo de sesiones de Claude Code (por defecto 20)
#   --max-horas H      parar tras H horas (por defecto 10)
#   --timeout-min M    máximo de minutos por sesión (por defecto 120)
#   --modelo M         modelo de Claude leader, p. ej. sonnet u opus
#   OPENCODE_WRITER_MODEL  modelo DeepSeek writer (por defecto deepseek/deepseek-flash)
#   --sin-commits      no hacer un commit de git después de cada sesión
#
# Cada sesión lanza `claude -p` con las instrucciones de .claude/nocturno.md
# y --permission-mode dontAsk (deniega en vez de preguntar). Lleva UNA
# feature hasta done o blocked. Al terminar (o con Ctrl+C) el arnés vuelve
# al modo en el que estaba.
#
# Se detiene si:
#   · no quedan features pending / spec_ready / in_progress
#   · ./init.sh queda en rojo tras una sesión
#   · dos sesiones seguidas no cambian nada en feature_list.json
#   · se alcanza --max-sesiones o --max-horas

set -u
cd "$(dirname "$0")"

# Evita que el ordenador se duerma mientras trabaja (macOS / Linux con systemd).
if [ -z "${NOCTURNO_DESPIERTO:-}" ]; then
  export NOCTURNO_DESPIERTO=1
  if command -v caffeinate >/dev/null 2>&1; then
    exec caffeinate -ims "$0" "$@"
  elif command -v systemd-inhibit >/dev/null 2>&1 && systemd-inhibit --what=idle true >/dev/null 2>&1; then
    exec systemd-inhibit --what=idle:sleep --why="nocturno.sh trabajando" "$0" "$@"
  fi
fi

MAX_SESIONES=20
MAX_HORAS=10
TIMEOUT_MIN=120
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

MODEL_FLAG=""
[ -n "$MODELO" ] && MODEL_FLAG="--model $MODELO"

TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT_CMD="timeout $((TIMEOUT_MIN * 60))";
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT_CMD="gtimeout $((TIMEOUT_MIN * 60))"; fi

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
for wanted in ("in_progress", "spec_ready", "pending"):
    for f in sorted(fs, key=lambda f: f["id"]):
        if f["status"] == wanted:
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

snapshot() { $PY -c 'import json;print(json.dumps([(f["id"],f["status"]) for f in json.load(open("feature_list.json",encoding="utf-8"))["features"]]))'; }

if [ -n "$(next_feature)" ] && ! opencode auth list 2>&1 | grep -qi 'deepseek'; then
  echo "[nocturno] Hay trabajo pendiente, pero DeepSeek no está conectado. Ejecuta /connect y configura el proveedor 'deepseek'." >&2
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
  echo "Límites: $MAX_SESIONES sesiones, $MAX_HORAS h, $TIMEOUT_MIN min/sesión. Commits: $([ $USE_GIT = 1 ] && echo sí || echo no)."
  echo
  echo "## Sesiones"
  echo
} > "$REPORT"

echo "[nocturno] Comprobando el entorno con ./init.sh..."
if ! bash ./init.sh > /dev/null 2>&1; then
  echo "- $(now) — init.sh en rojo ANTES de empezar. No se hizo nada." >> "$REPORT"
  echo "[nocturno] init.sh falla antes de empezar. Arréglalo y vuelve a lanzar." >&2
  exit 1
fi

# ── Bucle principal ───────────────────────────────────────────────────────
sesion=0
sin_cambios=0
motivo="sin trabajo pendiente"

while :; do
  next=$(next_feature)
  if [ -z "$next" ]; then motivo="no quedan features pendientes"; break; fi
  if [ "$sesion" -ge "$MAX_SESIONES" ]; then motivo="alcanzado --max-sesiones ($MAX_SESIONES)"; break; fi
  if [ $(( $(date +%s) - START )) -ge $(( MAX_HORAS * 3600 )) ]; then motivo="alcanzado --max-horas ($MAX_HORAS)"; break; fi

  IFS=$'\t' read -r fid fname fstatus <<< "${next//$'\r'/}"
  sesion=$((sesion + 1))
  echo "[nocturno] $(now) — sesión $sesion: feature #$fid $fname ($fstatus)"

  before=$(snapshot)
  {
    echo
    echo "════════ $(now) — sesión $sesion — #$fid $fname ($fstatus) ════════"
  } >> "$LOG"
  $TIMEOUT_CMD claude -p \
    "MODO NOCTURNO. Procesa la siguiente feature (#$fid $fname) siguiendo .claude/nocturno.md y termina." \
    --append-system-prompt-file .claude/nocturno.md \
    --permission-mode dontAsk $MODEL_FLAG \
    >> "$LOG" 2>&1 < /dev/null
  rc=$?
  after=$(snapshot)
  nuevo=$(status_of "$fid" | tr -d '\r')

  if bash ./init.sh > /dev/null 2>&1; then init_ok=1; init_txt="verde"; else init_ok=0; init_txt="ROJO"; fi
  [ "$rc" = "124" ] && extra=" (timeout)" || extra=""
  echo "- $(now) — #$fid \`$fname\`: $fstatus → **$nuevo** · init.sh $init_txt · exit $rc$extra" >> "$REPORT"
  echo "[nocturno]   → $nuevo, init.sh $init_txt"

  if [ "$USE_GIT" = "1" ] && [ -n "$(git status --porcelain)" ]; then
    git add -A -- . ":(exclude).claude/settings.json" ":(exclude).claude/settings.json.bak" && git commit -q -m "nocturno: #$fid $fname → $nuevo" || true
  fi

  if [ "$init_ok" = "0" ]; then motivo="init.sh quedó en rojo tras la sesión $sesion"; break; fi

  if [ "$before" = "$after" ]; then
    sin_cambios=$((sin_cambios + 1))
    if [ "$sin_cambios" -ge 2 ]; then
      motivo="dos sesiones seguidas sin avances (¿aceptaste el aviso de confianza de Claude Code en esta carpeta? mira progress/nocturno.log)"
      break
    fi
  else
    sin_cambios=0
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
