#!/usr/bin/env bash
# Prepara un servidor Ubuntu (p. ej. Oracle Cloud Always Free, ARM o x86) para
# el chatbot Lázaro. Idempotente: se puede volver a ejecutar sin romper nada.
#
# Uso (en el servidor, como usuario con sudo):
#   curl -fsSL https://raw.githubusercontent.com/wilsoncespedes-dot/Chatbot_lazaro/<rama>/deploy/oracle/instalar.sh | sudo bash
#
# Deja:
#   - Docker + compose, git y cloudflared instalados.
#   - El repositorio en /opt/lazaro siguiendo la rama $BRANCH.
#   - Un temporizador systemd que cada 2 minutos ejecuta deploy/actualizar.sh:
#     si hay commits nuevos en GitHub, reconstruye; si no, solo verifica que
#     los servicios sigan arriba (también tras reiniciar el servidor).
# No crea el `.env` ni el túnel: ver docs/despliegue_oracle.md.
set -euo pipefail

REPO="${REPO:-https://github.com/wilsoncespedes-dot/Chatbot_lazaro.git}"
BRANCH="${BRANCH:-feat/lazaro-backlog-complete}"
DIR="${DIR:-/opt/lazaro}"
APP_USER="${APP_USER:-${SUDO_USER:-ubuntu}}"
LOG_DIR=/var/log/lazaro

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este script con sudo." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git curl ca-certificates

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
usermod -aG docker "$APP_USER"

if ! command -v cloudflared >/dev/null 2>&1; then
  arch="$(dpkg --print-architecture)"
  curl -fsSL -o /tmp/cloudflared.deb \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb"
  dpkg -i /tmp/cloudflared.deb
  rm -f /tmp/cloudflared.deb
fi

if [ ! -d "$DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
chown -R "$APP_USER:$APP_USER" "$DIR"
install -d -o "$APP_USER" -g "$APP_USER" "$LOG_DIR"

cat >/etc/systemd/system/lazaro-actualizar.service <<EOF
[Unit]
Description=Chatbot Lazaro: desplegar commits nuevos
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$APP_USER
Environment=LAZARO_DEPLOY_DIR=$DIR
Environment=LAZARO_DEPLOY_BRANCH=$BRANCH
Environment=LAZARO_DEPLOY_LOG=$LOG_DIR/actualizar.log
ExecStart=/bin/bash $DIR/deploy/actualizar.sh
EOF

cat >/etc/systemd/system/lazaro-actualizar.timer <<'EOF'
[Unit]
Description=Chatbot Lazaro: revisar commits nuevos cada 2 minutos

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable lazaro-actualizar.timer

if [ -f "$DIR/.env" ]; then
  systemctl start lazaro-actualizar.timer
  echo "Listo: el temporizador está activo. Registro: $LOG_DIR/actualizar.log"
else
  echo "Falta $DIR/.env: cópialo y luego ejecuta"
  echo "  sudo systemctl start lazaro-actualizar.timer"
fi
