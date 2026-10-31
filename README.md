# Chatbot Lázaro Software

Chatbot de atención y soporte por **Telegram**: responde con los manuales
(RAG sobre pgvector), no inventa, y pasa la conversación a un **asesor
humano** cuando no puede resolver. Microservicios en **Python + FastAPI**, con
Docker, en un monorepo.

El desarrollo se hace con un **arnés SDD** (Spec Driven Development) para
**Claude Code**: un agente `leader` coordina, `spec_author` escribe el spec,
tú lo apruebas, `implementer` programa con tests y `reviewer` verifica.

- Contexto, decisiones y dudas abiertas: [`docs/proyecto.md`](docs/proyecto.md)
- Reglas técnicas: [`docs/architecture.md`](docs/architecture.md) y [`docs/conventions.md`](docs/conventions.md)
- Plan de trabajo: [`feature_list.json`](feature_list.json)

## Versión mínima (8 features)

| # | Feature | Qué entrega |
|---|---------|-------------|
| 1 | `contratos_servicios`   | `contracts/CONTRATOS.md` + modelos Pydantic compartidos |
| 2 | `esqueleto_servicios`   | 4 servicios FastAPI, Postgres+pgvector, Redis, Docker Compose, CI |
| 3 | `telegram_gateway`      | Webhook, descarte de repetidos, `POST /send` |
| 4 | `orquestador_basico`    | Contacto, historial, eventos, RAG → respuesta o traspaso |
| 5 | `rag_ingesta_busqueda`  | Carga de PDF/DOCX, fragmentos, búsqueda con umbral |
| 6 | `no_inventar`           | Validación de citas y números, rechazo fijo |
| 7 | `traspaso_asesor`       | Casos, aviso a asesores, tiempo de espera, respuesta del asesor |
| 8 | `evaluacion`            | Preguntas de ejemplo y métricas |

Para después: consulta a la base de datos, verificación de cuentas, paneles,
clasificador y edición de fragmentos (lista `later` en `feature_list.json`).

## Puesta en marcha (una vez)

En **Git Bash** (Windows) o una terminal (macOS/Linux):

```bash
cd ~/proyectos/chatbot-lazaro
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash)
# source .venv/bin/activate          # macOS / Linux
python -m pip install -r requirements-dev.txt
cp .env.example .env                 # y rellena tus claves; .env nunca va a git
./init.sh                            # debe terminar en [OK] Entorno listo
git init && git add -A && git commit -m "arnés del chatbot"
claude                               # acepta el aviso de confianza de la carpeta
```

`./init.sh` usa el `.venv` automáticamente si existe. Antes de la feature 2
dirá «Aún no hay tests»: es normal.

Cuando una feature añada dependencias (FastAPI, librerías de PDF…), el spec
las lista en `design.md` y el implementer las instala en el `.venv`. Para
instalarlas tú a mano en otro equipo:

```bash
python -m pip install -r services/<servicio>/requirements.txt
```

## Trabajo diario (modo supervisado)

1. En Claude Code: **`/siguiente`**. El leader lanza al spec_author y se para.
2. Lee `specs/<feature>/requirements.md`, `design.md` y `tasks.md`. Fíjate
   en **«Supuestos a confirmar»**: son decisiones de `docs/proyecto.md` §12
   que el spec tomó con un valor por defecto configurable.
3. Si está bien: **`/aprobar`**. Si no, pide cambios en el chat.
4. El implementer programa con tests y el reviewer verifica. Los informes
   quedan en `progress/impl_<feature>.md` y `progress/review_<feature>.md`.
5. **`/estado`** en cualquier momento para ver dónde estás.

## Modo nocturno

```bash
./modo.sh              # ¿en qué modo estoy?
git add -A && git commit -m "antes de dormir"
./nocturno.sh --max-sesiones 3
```

Trabaja feature tras feature sin preguntar: el reviewer aprueba los specs
por ti, hace un commit por feature y se para solo ante problemas. Por la
mañana: `progress/nocturno_<fecha>.md`, revisa los specs `"auto_approved"`
y usa `/revisado`.

Tu propio documento (D6) recomienda **empezar en supervisado**: de noche el
reviewer aprueba los specs en tu lugar y los agentes instalan las
dependencias que esos specs piden sin que nadie las revise antes.

## Permisos de los agentes

Los agentes tienen todo lo que necesitan para desarrollar: comandos de shell,
editar archivos, red (búsqueda web, `curl`, `git clone`), instalar
dependencias con pip y Docker.

| | Supervisado | Nocturno |
|---|---|---|
| Comandos, edición, red, pip, Docker | Sin preguntar | Sin preguntar |
| `git push`, `rm -rf`, `sudo`, `git reset --hard`, `git clean`, borrar volúmenes de Docker, `gh pr merge` | **Te pregunta** | **Denegado** |
| Editar el propio arnés (`docs/`, `CLAUDE.md`, `init.sh`, `.claude/`…) | Permitido | Denegado |
| Leer o editar `.env` | Denegado | Denegado |

- Solo instalan lo que está en el `requirements.txt` del servicio y en el
  `design.md` aprobado, dentro del `.venv` (regla de las instrucciones).
- Los repos de referencia van en `referencias/` (fuera de git, solo lectura).
- `init.sh` falla si un `.env` entra en git.
- Las reglas de Bash comparan texto, no son una barrera perfecta. Para más
  aislamiento, ejecuta en una máquina virtual.

## Trabajo en equipo

El arnés asume **una feature a la vez** por copia del repo. Si varios
integrantes trabajan en paralelo en ramas distintas, que cada uno tome una
feature diferente y el merge de `feature_list.json` y `progress/` se revise a
mano. Los contratos (feature 1) son los que permiten trabajar en paralelo
sin romperse: termínenla primero.

## Windows

- Python: [python.org](https://www.python.org/downloads/) o
  `winget install Python.Python.3.12`; desactiva los alias de la Microsoft
  Store (*Configuración → Aplicaciones → Configuración avanzada de
  aplicaciones → Alias de ejecución de aplicaciones*).
- Claude Code: `irm https://claude.ai/install.ps1 | iex` en PowerShell. Si
  Git Bash no encuentra `claude`:
  `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc`.
- Docker Desktop para la integración (feature 2 en adelante).
- Modo nocturno: `powercfg /change standby-timeout-ac 0` en PowerShell para
  que el equipo no se suspenda (vuelve con `... 30`).

## Estructura

```
.
├── AGENTS.md / CLAUDE.md     # Mapa para agentes / rol leader
├── CHECKPOINTS.md            # Criterios de estado final correcto
├── feature_list.json         # Las 8 features de la versión mínima
├── init.sh                   # Verificación: Python, pytest, secretos, specs, tests
├── modo.sh / nocturno.sh     # Modos supervisado / nocturno
├── pytest.ini / conftest.py  # Tests de todo el monorepo
├── requirements-dev.txt      # pytest, httpx
├── .env.example              # Variables (copia a .env)
├── THIRD_PARTY_NOTICES.md    # Código copiado y su licencia
├── docs/                     # proyecto, architecture, conventions, specs, verification
├── specs/<feature>/          # requirements.md, design.md, tasks.md
├── progress/                 # current.md, history.md, informes de agentes
├── contracts/                # (feature 1)
├── services/                 # (feature 2+) telegram_gateway, orchestrator, rag, handover
└── .claude/                  # agents, commands, hooks, modes, nocturno.md, settings.json
```
