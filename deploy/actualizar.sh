#!/usr/bin/env bash
# Mantiene el despliegue local al día con los commits de la rama vigilada.
#
# Corre sobre una copia dedicada del repositorio (por defecto
# ~/lazaro-despliegue), nunca sobre la carpeta de desarrollo: hace
# `git reset --hard`, así que cualquier cambio a mano en esa copia se pierde.
#
# Uso:  deploy/actualizar.sh            # actualiza si hay commits nuevos
#       deploy/actualizar.sh --forzar   # reconstruye aunque no haya cambios
#
# Variables opcionales:
#   LAZARO_DEPLOY_DIR     copia de despliegue (defecto: ~/lazaro-despliegue)
#   LAZARO_DEPLOY_BRANCH  rama a seguir (defecto: la que tenga la copia)
#   LAZARO_COMPOSE_PROJECT nombre del proyecto compose (defecto: chatbot-lazaro,
#                          el mismo de la carpeta de desarrollo, para reutilizar
#                          el volumen de Postgres)
set -uo pipefail

DIR="${LAZARO_DEPLOY_DIR:-$HOME/lazaro-despliegue}"
PROJECT="${LAZARO_COMPOSE_PROJECT:-chatbot-lazaro}"
LOG="${LAZARO_DEPLOY_LOG:-$HOME/lazaro-despliegue.log}"
LOCK="$DIR/.git/actualizar.lock"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

# Evita dos ejecuciones a la vez (la tarea programada corre cada pocos minutos).
if ! mkdir "$LOCK" 2>/dev/null; then
  # Un candado de más de 30 min es de una ejecución que murió: se libera.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || exit 0
  else
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$DIR" || { log "ERROR no existe $DIR"; exit 1; }
BRANCH="${LAZARO_DEPLOY_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

if ! docker info >/dev/null 2>&1; then
  log "Docker no responde; se reintenta en la próxima ejecución"
  exit 0
fi

if ! git fetch -q origin "$BRANCH" 2>>"$LOG"; then
  log "ERROR git fetch origin $BRANCH"
  exit 1
fi

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" != "$REMOTE" ] || [ "${1:-}" = "--forzar" ]; then
  git reset -q --hard "origin/$BRANCH"
  log "Desplegando $(git log -1 --format='%h %s')"
  if docker compose -p "$PROJECT" up --build -d --remove-orphans >>"$LOG" 2>&1; then
    log "OK desplegado $(git rev-parse --short HEAD)"
  else
    log "ERROR docker compose up (ver arriba); se reintenta en la próxima ejecución"
    git reset -q --hard "$LOCAL"
    exit 1
  fi
else
  # Sin commits nuevos: solo se asegura de que los servicios sigan arriba
  # (p. ej. tras reiniciar el PC). No reconstruye imágenes.
  docker compose -p "$PROJECT" up -d >/dev/null 2>>"$LOG" || log "ERROR docker compose up -d"
fi

# El registro no crece sin límite.
if [ -f "$LOG" ] && [ "$(wc -l <"$LOG")" -gt 2000 ]; then
  tail -n 1000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
