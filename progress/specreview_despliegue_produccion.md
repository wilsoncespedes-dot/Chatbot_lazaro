# Spec review — #24 despliegue_produccion (2ª corrección: R32)

**Veredicto:** APPROVED

## Bloqueos materiales
Ninguno.

## Verificación de la corrección
- **R32 / acceptance 6:** fija `ADMIN_TRUST_PROXY_HEADERS="true"` solo en `envVars` del orchestrator (no en `lazaro-compartido`), toma el **primer** valor de `X-Forwarded-For` y usa `request.client.host` si falta, está vacío o el primer valor está vacío. El pseudocódigo de `design.md` §«IP del cliente tras el proxy» cumple todos los casos. Hoy el código usa el último valor (`services/orchestrator/orchestrator/admin_routes.py:48`) y el test lo espera (`services/orchestrator/tests/test_admin.py:635-640`); `design.md` (tabla Archivos) y T14 nombran ambos cambios. Los tests de T8 (Blueprint + que no esté en el env group) y T14 (primer valor ≠ terminal, espacios, ausente/`""`/`" "`/`", x"` y que 5 fallos desde IPs distintas no bloqueen a un sexto cliente) cubren R32. Además aparece en «Supuestos a confirmar» y en «Alternativas descartadas».
- **Topología pública:** se mantienen exactamente dos `web` (gateway, orchestrator) con `/health`; rag/handover `pserv` y el worker privado (R1–R3). El panel exige sesión/CSRF y no se habilita con `X-Service-Token` (R31); las rutas internas devuelven 401 (R29, R30). No hay cambios desde la revisión anterior, que ya era coherente.
- **Resto de acceptance:** secretos (R8, R9, R12–R20), CI (R21–R22) y webhook (R23–R28) sin cambios y coherentes. Las tasks T1–T16 siguen en `[ ]` y cubren R1–R32.

## No bloqueante
- R8, R31 y R32 tienen más de un `DEBE` cada uno (EARS no estricto). Se puede verificar igual con los tests de T8/T14.
- Que el primer valor de `X-Forwarded-For` lo pueda falsificar el cliente depende de cómo lo trate el proxy de Render. Si se puede falsificar, el límite por IP se esquiva, pero el límite por usuario (`domain.py:708`) sigue frenando la fuerza bruta contra una cuenta. Es la decisión que tomó el acceptance, así que no se reabre.
- Sigue pendiente de la revisión anterior: aclarar en R23/`docs/despliegue.md` que `PUBLIC_BASE_URL` es la URL pública de **telegram-gateway**, no la del orchestrator.
