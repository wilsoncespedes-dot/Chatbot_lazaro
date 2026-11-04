# Spec review — #38 identidad_credenciales

**Veredicto:** CAMBIOS

Lo que está bien: la tabla de trazabilidad A1–A6 → R<n> está completa. La identidad vive en el orquestador y no se tocan contratos. Las contraseñas usan scrypt con prefijo y PBKDF2 sigue funcionando. El token es HMAC más una fila con hash y un solo uso, guardado de forma atómica con índices únicos parciales. Los valores por defecto son seguros y se pueden sobrescribir con `identity.*`. Desactivar el login en producción está prohibido (R50). Cada task es verificable y entre todas cubren todos los R<n>. El impacto de `IDENTITY_LOGIN_REQUIRED` es viable: las suites antiguas ponen `false` desde `conftest.py` (T17) y un test dedicado comprueba que con `true` el mensaje no llega a RAG.

## Cambios requeridos
1. Hoy R25 no se cumple. R25 prohíbe que el token en claro aparezca en los logs, pero `GET /acceso?t=<token>` (R1, R10) lo deja en el log de acceso de uvicorn, que incluye la query string. `services/orchestrator/Dockerfile:12` arranca uvicorn sin `--no-access-log`. Hay que añadir a `design.md` uno de estos dos mecanismos:
   - un filtro de logging sobre `uvicorn.access` que oculte el valor de `t=`, o
   - arrancar con `--no-access-log` y añadir `Dockerfile` a la tabla de archivos.

   Además hay que ampliar T21 o T19 con un test: emitir un registro de `uvicorn.access` con la ruta `/acceso?t=...` y comprobar que el token no aparece. En R25 también hay que precisar que el requisito cubre los logs del proceso del orquestador. Los logs del proxy de Render quedan fuera y deben anotarse como supuesto.

## Observaciones no bloqueantes
- R2 genera un enlace nuevo con cada mensaje en `awaiting_login`. Es aceptable porque R5 invalida los anteriores.
- En T15, comprobar que no se llama a `get_profile_by_telegram_user_id` mediante un spy está bien. Conviene comprobarlo en todo el flujo de `_route_consented_text`, no solo en `login_client`.

## Re-revisión

**Veredicto:** APROBADO. El cambio #1 quedó resuelto. R25 (requirements.md:157-162) ahora cubre los logs del proceso del orquestador, incluido `uvicorn.access` con `t=` redactado, y deja el proxy de Render fuera como supuesto. La fila de `main.py` en design.md:20 instala un `logging.Filter` idempotente sobre `uvicorn.access` y justifica por qué no se usa `--no-access-log`. El supuesto 9 (design.md:301-303) documenta los logs del proxy y cómo se mitigan. T21 (tasks.md:138-146) añade el test con un `LogRecord` de `uvicorn.access` que comprueba `t=***`.
Nota no bloqueante: R25 tiene dos «DEBE». Conviene unificarlos en uno al editar, pero no bloquea.
