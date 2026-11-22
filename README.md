# Chatbot Lázaro Software

Chatbot de atención y soporte por **Telegram y WhatsApp**: responde con los
manuales (RAG sobre pgvector), no inventa, identifica al cliente con login web
y pasa la conversación a un **asesor humano** en un panel propio cuando no
puede resolver. Microservicios en **Python + FastAPI**, con Docker, en un
monorepo.

- Qué hace el producto: [`docs/especificacion.md`](docs/especificacion.md)
- Contexto y decisiones: [`docs/proyecto.md`](docs/proyecto.md)
- Reglas técnicas: [`docs/architecture.md`](docs/architecture.md) y [`docs/conventions.md`](docs/conventions.md)
- Rutas entre servicios: [`contracts/CONTRATOS.md`](contracts/CONTRATOS.md)
- Despliegue en Render: [`docs/despliegue.md`](docs/despliegue.md)

## Abrir el proyecto en tu computador

### Qué necesitas instalado

| Herramienta | Para qué | Notas |
|---|---|---|
| Git | Descargar el repositorio | En Windows instala [Git for Windows](https://git-scm.com/download/win): trae **Git Bash** |
| Python 3.11 o superior (recomendado 3.12) | Correr los tests | Windows: `winget install Python.Python.3.12` y desactiva los alias de la Microsoft Store (*Configuración → Aplicaciones → Configuración avanzada de aplicaciones → Alias de ejecución de aplicaciones*) |
| Docker Desktop | Levantar los servicios | Solo si quieres ejecutar el bot; los tests no lo necesitan. Debe estar abierto y en marcha |

### 1. Descargar

Usa `git clone`. **No descargues el ZIP** de GitHub: no trae el historial y
luego no puedes actualizar con `git pull`.

```bash
git clone https://github.com/wilsoncespedes-dot/Chatbot_lazaro.git
cd Chatbot_lazaro
```

### 2. Instalar y comprobar (sin Docker)

En **Git Bash** (Windows) o en una terminal (macOS / Linux):

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash)
# source .venv/bin/activate          # macOS / Linux
python -m pip install -r requirements-dev.txt
cp .env.example .env
./init.sh                            # debe terminar en [OK] Entorno listo
```

En **PowerShell** (si no usas Git Bash):

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m pytest
```

Si PowerShell no deja activar el entorno, ejecuta una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Los scripts `.sh`
(`init.sh`, `modo.sh`, `nocturno.sh`) solo funcionan en Git Bash, no en
PowerShell ni en CMD.

Los tests usan adaptadores falsos: no necesitan Docker, base de datos, claves
ni internet (salvo para instalar las dependencias).

### 3. Levantar los servicios (con Docker)

Con Docker Desktop abierto y el `.env` creado en el paso anterior:

```bash
docker compose up --build
```

| Servicio | URL local |
|---|---|
| telegram_gateway | http://localhost:8001/health |
| orchestrator (panel en `/admin` y `/asesor`) | http://localhost:8002/health |
| rag | http://localhost:8003/health |
| handover | http://localhost:8004/health |

Con los valores de `.env.example` los servicios arrancan, pero el bot no
conversa hasta que rellenes en `.env` tus propias claves: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_WEBHOOK_SECRET`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDINGS_API_KEY` y
`EMBEDDINGS_MODEL`. **Nunca subas `.env` a git** ni compartas las claves por
chat; cada persona usa las suyas.

Crear el primer administrador del panel (pide la contraseña sin mostrarla):

```bash
docker compose exec orchestrator python -m orchestrator.bootstrap_admin --username <nombre>
```

Cargar un manual (PDF o DOCX) desde tu computador. El script lee las variables
del entorno, no del `.env`, y desde fuera de Docker el servicio `rag` está en
el puerto 8003:

```bash
RAG_URL=http://localhost:8003 SERVICE_TOKEN=<el de tu .env> python scripts/cargar_manual.py <ruta> --nombre <nombre>
```

Para que Telegram entregue mensajes hace falta una URL pública `https` y
registrar el webhook con `scripts/configurar_webhook.py`; el procedimiento está
en [`docs/despliegue.md`](docs/despliegue.md) §4.

### Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `python` abre la Microsoft Store o no existe | Instala Python y desactiva los alias de la Store; en PowerShell usa `py -3` |
| `./init.sh: command not found` o no hace nada | Estás en PowerShell o CMD: abre Git Bash |
| `pytest no está instalado` | No activaste el `.venv` o falta `python -m pip install -r requirements-dev.txt` |
| `docker compose` dice que no encuentra `.env` | Falta `cp .env.example .env` |
| `failed to connect to the docker API` | Docker Desktop no está abierto |
| El puerto 8001–8004 está ocupado | Cierra el programa que lo usa o cambia el puerto en `docker-compose.yml` |
| Faltan archivos o funciones recientes | Estás en una rama vieja: `git fetch` y `git switch <rama>` |

## Estructura

```
.
├── contracts/         # CONTRATOS.md + modelos Pydantic compartidos (lazaro_contracts)
├── services/          # telegram_gateway (Telegram y WhatsApp), orchestrator, rag, handover
├── eval/              # Evaluación con preguntas de ejemplo y casos de ataque
├── scripts/           # cargar_manual, configurar_webhook, workers de vencimiento y purga
├── docs/              # especificacion, proyecto, architecture, conventions, despliegue…
├── docker-compose.yml # Postgres (pgvector), Redis, servicios y workers
├── render.yaml        # Blueprint de Render
├── .env.example       # Variables (copia a .env)
├── requirements-dev.txt / pytest.ini / conftest.py
└── Arnés de agentes: AGENTS.md, CLAUDE.md, CHECKPOINTS.md, feature_list.json,
    init.sh, modo.sh, nocturno.sh, progress/, specs/, .claude/, .opencode/
```

## Desarrollo con agentes de IA (opcional)

No hace falta para abrir, probar ni ejecutar el proyecto. El desarrollo se
hace con un **arnés SDD** (Spec Driven Development): Claude Code coordina
(`leader`, `spec_author`, `reviewer`) y, con el spec aprobado, **OpenCode con
DeepSeek escribe el código**. El mapa para agentes es [`AGENTS.md`](AGENTS.md).

- `feature_list.json`: lista de features. Las `done` están resumidas; su
  descripción, spec e informes completos quedaron en el tag git
  `archivo-antes-limpieza-2026-11-15`.
- **`/siguiente`** en Claude Code: toma la siguiente feature pendiente (spec →
  revisión → implementación → `./init.sh` → revisión de código).
- **`/estado`**: resumen del arnés y de las features.

### Modos

```bash
./modo.sh                      # muestra el modo actual
./modo.sh supervisado          # por defecto
./nocturno.sh                  # sin topes; reintenta hasta agotar trabajo elegible
# ./nocturno.sh --max-sesiones 3 --max-horas 2 # límites opcionales
# ./nocturno.sh --sin-commits   # úsalo si ya tienes cambios locales sin commit
```

Por defecto, `0` significa sin límite de sesiones, horas ni minutos por sesión.
Ante sesiones sin avance verificable o fallos de `./init.sh`, reintenta con una
espera creciente. El ciclo respeta dependencias y termina cuando no queda una
feature accionable, o cuando indicas un límite o interrumpes el proceso. En modo
nocturno el reviewer aprueba los specs en tu lugar; por la mañana revisa los que
tengan `"auto_approved"` y usa `/revisado`.

| | Supervisado | Nocturno |
|---|---|---|
| Comandos, edición, red, pip, Docker | Sin preguntar | Sin preguntar |
| `git push`, `rm -rf`, `sudo`, `git reset --hard`, `git clean`, borrar volúmenes de Docker, `gh pr merge` | **Te pregunta** | **Denegado** |
| Editar el propio arnés (`docs/`, `CLAUDE.md`, `init.sh`, `.claude/`…) | Permitido | Denegado |
| Leer o editar `.env` | Denegado | Denegado |

Las reglas de Bash comparan texto, no son una barrera perfecta. Para más
aislamiento, ejecuta en una máquina virtual.

### Conectar OpenCode Go (una vez por persona)

En el CLI de OpenCode ejecuta `/connect`, selecciona **Other**, usa el id de
proveedor `opencode-go` y configura tu credencial. Se guarda en el almacén de
OpenCode del usuario, fuera del repositorio. Comprueba que `OpenCode Go`
aparece en `opencode auth list`. El writer está fijado a
`opencode-go/deepseek-v4.1-flash` en ambos modos; su shell, red y subagentes
están bloqueados y solo edita archivos del proyecto.

### Trabajo en equipo

El arnés asume **una feature a la vez** por copia del repo. Si varias personas
trabajan en paralelo, cada una toma una feature distinta en su propia rama y el
merge de `feature_list.json` y `progress/` se revisa a mano. Los contratos de
`contracts/` son los que permiten trabajar en paralelo sin romperse.
