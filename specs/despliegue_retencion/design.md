# Design — despliegue_retencion (feature #28)

## 1. Alcance

Cierra los riesgos A–C de `progress/review_privacidad_y_retencion_datos.md`. Solo cambian
configuración, documentación y tests:

| Archivo | Cambio |
|---|---|
| `render.yaml` | nuevo `retention-worker`; `PRIVACY_*` en orchestrator y handover |
| `docs/despliegue.md` | worker, variables, bloqueo por valores del dueño, retención residual |
| `scripts/tests/test_render_retencion.py` (nuevo) | tests R1–R23 |

Sin cambios en `services/`, `contracts/`, `scripts/purgar_datos.py`, `docker-compose.yml`,
`.env.example` ni en `services/handover/Dockerfile` (ya copia el script, #27 R48). Sin
dependencias nuevas (`pyyaml` ya lo usa `test_render_blueprint.py`).

## 2. Blueprint

### 2.1 `retention-worker` (R1–R9)

Calco de `timeouts-worker` (#24):

```yaml
  - type: worker
    name: retention-worker
    runtime: docker
    region: virginia
    dockerContext: .
    dockerfilePath: services/handover/Dockerfile
    dockerCommand: python purgar_datos.py --intervalo
    envVars:
      - fromGroup: lazaro-compartido
      - key: HANDOVER_URL
        fromService: {type: pserv, name: handover, property: hostport}
      - key: ORCHESTRATOR_URL
        fromService: {type: web, name: orchestrator, property: hostport}
      - key: PRIVACY_PURGE_INTERVAL_SECONDS
        value: "86400"
      - key: PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS
        value: "120"
```

- **Comando:** la imagen de handover copia `scripts/purgar_datos.py` a `/app/purgar_datos.py`
  (Dockerfile línea 10); en la imagen no existe `scripts/`. Así, `python purgar_datos.py
  --intervalo` ejecuta `scripts/purgar_datos.py`, igual que `retention_worker` en compose. R3
  lo comprueba en el Dockerfile para que no se rompa el vínculo.
- **Contratos:** el script importa `lazaro_contracts.production`; la imagen tiene
  `/app/lazaro_contracts` y `/app` está en `sys.path` por ser el directorio del script.
- **Sin puertos:** un `worker` de Render no recibe tráfico. Hereda `PORT=8000` del grupo
  compartido igual que `timeouts-worker`; el script no lo usa y no abre ningún socket.
- **Valores de R8:** son parámetros del mecanismo, no plazos legales. Se copian de
  `.env.example` para que se vean en el panel; el test los compara con `.env.example`. El
  timeout acotado sostiene la demostración de #27 design §2.1 (2 × timeout ≪ 1 día).
- **Mínimo privilegio (R9):** el worker solo habla HTTP con `X-Service-Token`; no recibe
  `DATABASE_URL` ni plazos.

### 2.2 `PRIVACY_*` (R10–R16)

| Variable | Servicio | Forma |
|---|---|---|
| `PRIVACY_NOTICE_TEXT`, `PRIVACY_NOTICE_VERSION`, `PRIVACY_ACCEPT_PHRASE`, `PRIVACY_ACCEPTED_REPLY` | orchestrator | `sync: false` |
| `PRIVACY_RETENTION_DAYS` | handover | `sync: false` (**única fuente**) |
| `PRIVACY_RETENTION_DAYS` | orchestrator | `fromService: {type: pserv, name: handover, envVarKey: PRIVACY_RETENTION_DAYS}` |
| `PRIVACY_ACTIVE_CASE_MAX_DAYS` | handover | `sync: false` |

El reparto coincide con `REQUIRED_IN_PRODUCTION` de cada servicio (#27 R1 y R29). Los tests
escriben estas listas explícitamente y no importan código de los servicios.

**Valor compartido:** la demostración de #27 §2.1 exige el mismo `PRIVACY_RETENTION_DAYS` en
los dos servicios y ningún código lo comprueba. Hay una sola entrada `sync: false` (en
handover, junto a `PRIVACY_ACTIVE_CASE_MAX_DAYS`, porque handover valida `active < retention`
localmente, #27 R31) y el orchestrator la referencia con `envVarKey`. Este campo existe en el
esquema oficial `https://render.com/schema/render.yaml.json` (`envVarFromService.fromService.envVarKey`).

## 3. Firmas nuevas

No hay código de producción. Tests en `scripts/tests/test_render_retencion.py`, que reutilizan
el patrón de `test_render_blueprint.py` (`yaml.safe_load`, helpers `_service`, `_env_var`):

- `test_r1_retention_worker_uses_handover_image` … `test_r23_docs_list_uncovered_personal_data`,
  un test o más por `R<n>`; el docstring empieza por `R<n>:`.
- R8 lee `.env.example` línea a línea (`KEY=valor`); no lee `.env`.
- R22 usa la regex `PRIVACY_(RETENTION|ACTIVE_CASE_MAX)_DAYS\s*[=:]\s*\d` sobre el documento.

No se editan los tests de #24: siguen pasando sin cambios (los conjuntos `web` y `pserv` no
cambian y el worker comparte región).

## 4. Excepciones

No aplica. No hay rutas ni código nuevo. Un fallo de configuración en Render ya lo cubre
`ProductionConfigError` (#23, #27), que solo nombra variables.

## 5. Alternativas descartadas

- **`PRIVACY_RETENTION_DAYS` en el env group `lazaro-compartido`** (lo recomendaba la revisión
  de #27): Render no admite `sync: false` dentro de un env group (lo ignora, según
  `https://render.com/docs/blueprint-spec`). Usar `value` obligaría a versionar un plazo que
  no está aprobado. La referencia `envVarKey` da una sola fuente sin escribir un valor.
- **`dockerCommand: python scripts/purgar_datos.py --intervalo`**: esa ruta no existe en la
  imagen y el worker fallaría al arrancar.
- **Cron job de Render en lugar de worker:** cambiaría el modelo ya probado
  (`--intervalo`, compose, `timeouts-worker`) y el criterio de aceptación pide un worker.
- **`sync: false` independiente en cada servicio:** permite dos plazos distintos y rompe la
  coherencia de #27 §2.1 sin que nada lo detecte.

## 6. Supuestos a confirmar

| Id | Supuesto | Efecto mientras falte |
|---|---|---|
| S1 | El dueño define aviso, versión, frase, respuesta, `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` con revisión legal (#27 design §6, S1–S6). Este spec no fija ningún valor. | orchestrator y handover no arrancan en producción; el worker registra `privacy_purge_failed` |
| S2 | Render resuelve `envVarKey` sobre un valor `sync: false` de un `pserv` al crear el Blueprint. Validado contra el esquema, no con un despliegue real (esta feature no despliega). | si Render lo rechaza, el humano lo verá al crear el Blueprint; reabrir esta feature |
| S3 | `PRIVACY_PURGE_INTERVAL_SECONDS=86400` y `PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS=120` son defaults técnicos de #27, editables en el panel. | — |

**Riesgos informativos documentados, no resueltos aquí** (revisión de #27): TOCTOU purga ↔
mensaje en curso, update marcado antes del consentimiento, `500` síncrono si cae la BD,
`contacts` del personal sin consentimiento (debe constar en el aviso), logs y copias de
seguridad de Render, y supresión individual. R23 lleva a `docs/despliegue.md` solo los que
afectan al operador; el resto queda en la revisión de #27, sin duplicarlos.

## 7. Trazabilidad diseño → requirements

| Pieza | R |
|---|---|
| `retention-worker` en `render.yaml` | R1–R9 |
| `PRIVACY_*` en `render.yaml` | R10–R16 |
| `docs/despliegue.md` | R17–R23 |
| `scripts/tests/test_render_retencion.py` + `./init.sh` | R24 |
