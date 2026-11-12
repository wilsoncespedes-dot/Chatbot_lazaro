# Design — health checks de dependencias (#47)

## Alcance

`GET /health` sigue siendo público y no requiere `X-Service-Token`. El probe describe dependencias necesarias para el servicio y no ejecuta operaciones de negocio. Las dependencias de esta feature son Redis para `telegram_gateway` (deduplicación) y PostgreSQL para `orchestrator`, `rag` y `handover` (persistencia). El cliente de embeddings del servicio RAG y los servicios HTTP aguas arriba no se prueban en esta iteración: el proyecto no usa Ollama y no se debe añadir una dependencia externa al healthcheck.

Una dependencia responde saludable cuando su probe termina dentro del límite configurado; cualquier excepción o timeout se reporta como fallo. No se incluyen mensajes de excepción, URL ni configuración sensible en la respuesta HTTP. Un servicio con adaptadores falsos en tests conserva el comportamiento inyectado y no abre conexiones de red.

## Archivos a crear o modificar

- `contracts/lazaro_contracts/common.py`: permitir los estados `ok` y `unhealthy` en `HealthResponse`, con detalles opcionales por dependencia para el estado degradado.
- `contracts/CONTRATOS.md`: documentar que `GET /health` conserva HTTP 200 y el cuerpo actual al estar saludable, y responde HTTP 503 con nombres de dependencias fallidas al estar no saludable; indicar que la ruta sigue siendo pública y no expone detalles sensibles.
- `contracts/examples/health_response.json` y un ejemplo nuevo `contracts/examples/health_unavailable_response.json`: cubrir los cuerpos saludable y no saludable del modelo actualizado.
- `contracts/tests/test_models.py`, `contracts/tests/test_examples.py` y `contracts/tests/test_contratos_doc.py`: validar ambos estados, el rechazo de valores inválidos, los dos ejemplos y la documentación de las respuestas.
- `services/telegram_gateway/telegram_gateway/adapters/dedup.py`: añadir una operación de disponibilidad Redis de solo lectura (`PING`) al protocolo y al fake.
- `services/telegram_gateway/telegram_gateway/config.py`, `.env.example` y `services/telegram_gateway/telegram_gateway/main.py`: configurar el límite del probe, consultar Redis y responder 503 cuando falle o expire el timeout.
- `services/orchestrator/orchestrator/config.py` y `services/orchestrator/orchestrator/adapters/repository.py`: configurar el límite y añadir `health_check()` al protocolo/repositorio y fake; PostgreSQL abre una conexión acotada independiente y ejecuta solo `SELECT 1`, sin invocar inicialización de esquema.
- `services/orchestrator/orchestrator/main.py`: incluir el resultado del repositorio en `/health`.
- `services/rag/rag/config.py`, `services/rag/rag/adapters/repository.py` y `services/rag/rag/main.py`: probe `SELECT 1` inyectable y resultado de `/health`.
- `services/handover/handover/config.py`, `services/handover/handover/adapters/repository.py` y `services/handover/handover/main.py`: probe `SELECT 1` inyectable y resultado de `/health`.
- `docker-compose.yml`: añadir healthcheck HTTP a los cuatro servicios de aplicación y healthcheck `redis-cli ping`; ajustar dependencias de arranque que requieren Redis/PostgreSQL para esperar a `healthy`.
- Tests de contratos y de cada servicio afectado; `progress/impl_healthcheck_dependencias.md` para trazabilidad.

Las funciones nuevas de repositorio comparten la firma `health_check(timeout_seconds: float) -> None`: finalizan normalmente si hay conexión y lanzan la excepción técnica al caller; la capa HTTP convierte cualquier fallo en estado no saludable sin serializar la excepción. Cada prueba de PostgreSQL abre una conexión independiente limitada por `timeout_seconds`, ejecuta `SELECT 1` y cierra esa conexión, sin invocar `_connection()` ni sus migraciones. El probe de Redis es `ping(timeout_seconds: float) -> bool` y devuelve falso o lanza una excepción ante fallo; su cliente aplica límites de conexión y socket. Se usa `HEALTHCHECK_TIMEOUT_SECONDS` con default 2 segundos y límites positivos en configuración por servicio; el cliente/adaptador aplica ese límite al probe.

## Contrato documentado y ejemplos

La sección `Salud` de `contracts/CONTRATOS.md` define ambos resultados: saludable es HTTP 200 con el cuerpo actual; no saludable es HTTP 503 y el cuerpo con `status = unhealthy` y el mapa `dependencies`. Ambos ejemplos JSON validan contra `HealthResponse`. Las pruebas de contrato comprueban los dos estados válidos, rechazan estados/campos inválidos, validan los ejemplos y verifican que la documentación mencione el HTTP status y el contenido de cada respuesta.

## Respuesta HTTP

- Saludable: cuerpo actual exacto `{"status":"ok","service":"<nombre>"}` y HTTP 200.
- No saludable: HTTP 503 y `{"status":"unhealthy","service":"<nombre>","dependencies":{"postgres":"unavailable"}}` o `{"status":"unhealthy","service":"telegram_gateway","dependencies":{"redis":"unavailable"}}`.
- Una dependencia que excede el timeout también se representa como `unavailable`; no se retorna texto del error, DSN, hostname, usuario ni contraseña.

El detalle `dependencies` se omite cuando todas las dependencias están saludables para conservar el cuerpo vigente. `HealthResponse` continúa siendo el modelo compartido.

## Timeout y concurrencia

El límite del probe se configura con `HEALTHCHECK_TIMEOUT_SECONDS` (default 2, máximo 10) y se declara en `.env.example`. No se cambia el timeout de peticiones de negocio. Cada probe usa un cursor/llamada de solo lectura; no inicializa esquemas ni ejecuta migraciones. El healthcheck Docker llama `http://127.0.0.1:8000/health` con Python stdlib disponible en las imágenes base y usa un timeout finito. Redis usa `redis-cli ping`.

## Alternativa descartada

No se hará una llamada al LLM ni al endpoint de embeddings en cada healthcheck. Esas dependencias son externas, agregan latencia y falsos negativos por indisponibilidad ajena; tampoco existe Ollama en esta arquitectura. La primera versión mide persistencia y deduplicación, dependencias locales requeridas por los servicios.

## Dependencias

No se agregan paquetes. Se reutilizan drivers existentes (`redis`, `psycopg`) y Python stdlib en los healthchecks de Compose.
