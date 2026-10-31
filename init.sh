#!/usr/bin/env bash
# init.sh — Verificación e inicialización del entorno
#
# Lo ejecuta el agente al COMENZAR una sesión y antes de declarar cualquier
# tarea como `done`. Si falla, la sesión no debe avanzar.
#
# Salida esperada: códigos de salida claros y bloques marcados con [OK]/[FAIL].

set -u
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
fail()  { printf "${RED}[FAIL]${NC}  %s\n" "$1"; }

# shellcheck source=.claude/hooks/find_python.sh
source .claude/hooks/find_python.sh

EXIT_CODE=0

echo "── 1. Verificando entorno ─────────────────────────────"

if [ -z "$PY" ]; then
  fail "No se encontró Python. Instala Python >= 3.11 (en Windows: python.org o"
  fail "'winget install Python.Python.3.12') y desactiva los alias de la Microsoft Store."
  exit 1
fi
ok "Python -> $PY ($($PY --version 2>&1 | tr -d '\r'))"

PY_VERSION_OK=$($PY -c 'import sys; print(int(sys.version_info >= (3, 11)))' | tr -d '\r')
if [ "$PY_VERSION_OK" != "1" ]; then
  fail "Se requiere Python >= 3.11"
  exit 1
fi
ok "Versión de Python compatible"

if ! $PY -m pytest --version >/dev/null 2>&1; then
  fail "pytest no está instalado. Ejecuta: $PY -m pip install -r requirements-dev.txt"
  exit 1
fi
ok "pytest disponible"

echo ""
echo "── 2. Verificando archivos base del arnés ──────────────"

for f in AGENTS.md feature_list.json progress/current.md docs/proyecto.md \
         docs/architecture.md docs/conventions.md docs/verification.md docs/specs.md \
         CHECKPOINTS.md .env.example; do
  if [ ! -f "$f" ]; then
    fail "Falta archivo base: $f"
    EXIT_CODE=1
  else
    ok "Existe $f"
  fi
done

echo ""
echo "── 3. Secretos ─────────────────────────────────────────"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked=$(git ls-files -- .env '.env.*' '**/.env' '**/.env.*' | grep -v '\.env\.example$' || true)
  if [ -n "$tracked" ]; then
    fail "Hay archivos de secretos en git: $(echo $tracked). Quítalos con 'git rm --cached'"
    EXIT_CODE=1
  else
    ok "Ningún .env está en git"
  fi
else
  warn "No es un repositorio git todavía (git init)"
fi

echo ""
echo "── 4. Validando feature_list.json y specs ─────────────"

$PY - <<'PY'
import json, os, sys
try:
    data = json.load(open("feature_list.json", encoding="utf-8"))
    valid = {"pending", "spec_ready", "in_progress", "done", "blocked"}
    in_progress = [f for f in data["features"] if f["status"] == "in_progress"]
    if len(in_progress) > 1:
        print(f"[FAIL]  Hay {len(in_progress)} features en in_progress (máximo 1)")
        sys.exit(1)
    requires_spec = {"spec_ready", "in_progress", "done"}
    spec_errors = []
    for f in data["features"]:
        if f["status"] not in valid:
            print(f"[FAIL]  Estado inválido en feature {f['id']}: {f['status']}")
            sys.exit(1)
        if f.get("sdd") and f["status"] in requires_spec:
            spec_dir = os.path.join("specs", f["name"])
            for fname in ("requirements.md", "design.md", "tasks.md"):
                if not os.path.isfile(os.path.join(spec_dir, fname)):
                    spec_errors.append(
                        f"feature {f['id']} ({f['name']}) en {f['status']} "
                        f"sin {spec_dir}/{fname}"
                    )
    if spec_errors:
        for e in spec_errors:
            print(f"[FAIL]  {e}")
        sys.exit(1)
    print(f"[OK]    feature_list.json válido ({len(data['features'])} features)")
    print(f"[OK]    Specs presentes para features sdd con estado no-pending")
except SystemExit:
    raise
except Exception as e:
    print(f"[FAIL]  feature_list.json o specs inválidos: {e}")
    sys.exit(1)
PY

if [ $? -ne 0 ]; then EXIT_CODE=1; fi

echo ""
echo "── 5. Ejecutando tests (pytest) ────────────────────────"

$PY -m pytest 2>&1
rc=$?
if [ $rc -eq 0 ]; then
  ok "Todos los tests pasan"
elif [ $rc -eq 5 ]; then
  warn "Aún no hay tests (normal antes de la feature 2: esqueleto de servicios)"
else
  fail "Hay tests rotos (pytest salió con código $rc)"
  EXIT_CODE=1
fi

echo ""
echo "── 6. Modo del arnés ───────────────────────────────────"

ok "Modo actual: $(bash ./modo.sh --actual)"

echo ""
echo "── 7. Resumen ──────────────────────────────────────────"

if [ $EXIT_CODE -eq 0 ]; then
  ok "Entorno listo. Puedes empezar a trabajar."
else
  fail "Entorno NO está listo. Resuelve los errores antes de avanzar."
fi

exit $EXIT_CODE
