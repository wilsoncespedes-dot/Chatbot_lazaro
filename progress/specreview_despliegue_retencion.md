# Spec review — feature #28 despliegue_retencion

**Veredicto:** SPEC_APPROVED

## Puntos verificados

1. **Ruta de `purgar_datos.py` en la imagen.** Es correcta. `services/handover/Dockerfile:3` fija
   `WORKDIR /app` y `:10` copia `scripts/purgar_datos.py` a `./purgar_datos.py`, es decir, a
   `/app/purgar_datos.py`. `dockerCommand: python purgar_datos.py --intervalo` (R2) se resuelve
   igual que `timeouts-worker` (`render.yaml:131`) y que compose (`docker-compose.yml:55`).
   Importación de contratos: en la imagen, `scripts/purgar_datos.py:18-20` busca `/contracts`, que
   no existe, así que no añade nada. Pero `sys.path[0]` es `/app`, donde está `lazaro_contracts`
   (Dockerfile:7). `httpx` está en `services/handover/requirements.txt:5`. R3 protege el vínculo
   COPY ↔ comando. La alternativa `scripts/purgar_datos.py` se descarta con razón.
2. **`fromService` y `envVarKey`.** `{type: pserv, name: handover, envVarKey: PRIVACY_RETENTION_DAYS}`
   tiene la forma documentada del Blueprint spec de Render: `envVarKey` sustituye a `property`. Las
   referencias `hostport` de R6/R7 copian el patrón ya probado en `render.yaml:136-139`. El punto
   abierto es si Render resuelve una referencia a un valor `sync: false`. S2 lo documenta, es
   reversible y lo detecta el humano al crear el Blueprint. No bloquea.
3. **Un único `PRIVACY_RETENTION_DAYS`.** R11, R12 y R13 dejan una sola fuente (`sync: false` en
   handover) y el orchestrator la recibe por referencia. Esto cumple el criterio de aceptación 2 y
   la coherencia de #27 §2.1. Que viva en handover también es coherente: allí está la validación
   `active < retention` (#27 R31). Descartar el env group está justificado: un env group no admite
   `sync: false` y la alternativa sería un `value` versionado. R19 documenta que hay que redesplegar
   los dos servicios tras cambiar el valor.
4. **No inventar valores del dueño.** R14 prohíbe `value`/`generateValue` en las seis variables
   legales, en servicios y en env groups. R22 prohíbe ejemplos numéricos en la documentación. R21
   y S1 dejan la decisión al propietario, con revisión legal. Los únicos valores escritos (R8:
   `86400` y `120`) son parámetros técnicos y se comparan con `.env.example:115-116`, no se
   inventan. El reparto de R10, R11 y R16 coincide con `REQUIRED_IN_PRODUCTION`
   (`orchestrator/config.py:31-35`, `handover/config.py:24-25`).
5. **Feedback de #27.** El spec cubre A (R1–R9), B (R10–R16) y C (R17–R23). R23 traslada al
   operador los datos que la purga no cubre.
6. **Compatibilidad con #24.** `test_render_blueprint.py` no cambia. Los conjuntos `web` y `pserv`
   siguen iguales, `test_r6` (misma región) pasa con `region: virginia` y R4 refuerza
   `test_r1`. Las tasks T1–T9 están en `[ ]`, en orden, y entre todas cubren R1–R24.

## Notas no bloqueantes (para el implementador)

- R4 y R13 contienen dos `DEBE` cada uno. El EARS no es estricto, pero los dos se pueden verificar
  sin ambigüedad. No hace falta reabrir el spec.
- El test de R12 debe comprobar que la entrada no tiene `property` ni `value`/`sync`, y que
  `envVarKey` coincide exactamente con la `key` declarada en handover.
- El test de R9 debe tratar `fromGroup` como una entrada válida sin `key`, igual que `_env_var`.
