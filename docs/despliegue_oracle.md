# Despliegue en Oracle Cloud (Always Free) con Cloudflare Tunnel

Un solo servidor corre el mismo `docker-compose.yml` que en local. Se actualiza
solo: un temporizador systemd revisa GitHub cada 2 minutos y, si hay commits
nuevos en la rama desplegada, reconstruye los servicios (`deploy/actualizar.sh`).
No se abren puertos: el tráfico entra por un Cloudflare Tunnel con nombre.

| Pieza | Valor |
|---|---|
| Servidor | VM Ampere A1 (ARM), Ubuntu, usuario `ubuntu` |
| Código | `/opt/lazaro`, rama `feat/lazaro-backlog-complete` |
| Registro de despliegues | `/var/log/lazaro/actualizar.log` |
| Webhook de Telegram | `https://bot.chatbotlazaro.dpdns.org` → telegram_gateway (8001) |
| Paneles y enlace de verificación | `https://panel.chatbotlazaro.dpdns.org` → orchestrator (8002) |

## 1. Crear la VM (humano, en la consola de Oracle)

1. Compute → Instances → Create instance.
2. Imagen: Ubuntu 24.04. Forma: `VM.Standard.A1.Flex` (Always Free, hasta
   4 OCPU y 24 GB). Si dice "Out of capacity", prueba otro dominio de
   disponibilidad o vuelve a intentar más tarde.
3. SSH: pega la clave pública (`~/.ssh/lazaro_oracle.pub` del PC de desarrollo).
4. No hace falta abrir puertos en la VCN: el túnel solo sale hacia Cloudflare.

## 2. Preparar el servidor

```bash
ssh -i ~/.ssh/lazaro_oracle ubuntu@<IP>
curl -fsSL https://raw.githubusercontent.com/wilsoncespedes-dot/Chatbot_lazaro/feat/lazaro-backlog-complete/deploy/oracle/instalar.sh | sudo bash
```

## 3. Copiar el `.env` (humano; nunca al repositorio)

En el `.env` del servidor:
`IDENTITY_PUBLIC_BASE_URL=https://panel.chatbotlazaro.dpdns.org`.

```bash
scp -i ~/.ssh/lazaro_oracle .env ubuntu@<IP>:/opt/lazaro/.env
ssh -i ~/.ssh/lazaro_oracle ubuntu@<IP> sudo systemctl start lazaro-actualizar.timer
```

La base de datos del servidor empieza vacía: crea el administrador
(`docker compose -p chatbot-lazaro exec orchestrator python -m orchestrator.bootstrap_admin --username <nombre>`)
y vuelve a cargar los manuales (`scripts/cargar_manual.py`).

## 4. Túnel con nombre

En un PC con `cloudflared`: `cloudflared tunnel login` (autoriza el dominio en
el navegador), `cloudflared tunnel create lazaro` y
`cloudflared tunnel route dns lazaro bot.chatbotlazaro.dpdns.org` (igual para
`panel`). Copia el JSON de credenciales del túnel al servidor en
`/etc/cloudflared/` junto con este `config.yml`, y ejecuta
`sudo cloudflared service install`:

```yaml
tunnel: <ID del túnel>
credentials-file: /etc/cloudflared/<ID del túnel>.json
ingress:
  - hostname: bot.chatbotlazaro.dpdns.org
    service: http://localhost:8001
  - hostname: panel.chatbotlazaro.dpdns.org
    service: http://localhost:8002
  - service: http_status:404
```

Por último, registra el webhook (§4 de `docs/despliegue.md`) con
`PUBLIC_BASE_URL=https://bot.chatbotlazaro.dpdns.org`.

## Operación

- Desplegar: commit y `git push` a la rama. En ≤ 2 min queda en el servidor.
- Ver el registro: `tail -f /var/log/lazaro/actualizar.log`.
- Forzar reconstrucción: `sudo -u ubuntu LAZARO_DEPLOY_DIR=/opt/lazaro bash /opt/lazaro/deploy/actualizar.sh --forzar`.
- No edites `/opt/lazaro` a mano: `actualizar.sh` hace `git reset --hard`.
