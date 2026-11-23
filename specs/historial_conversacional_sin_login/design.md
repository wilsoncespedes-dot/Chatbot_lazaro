# Design — historial_conversacional_sin_login

## Alcance

Resolver el caso de despliegues con `IDENTITY_LOGIN_REQUIRED=false` donde la
persona ya conversó en el mismo chat pero no inició sesión en una cuenta de
cliente. El flujo casual ya persiste los mensajes del usuario y las respuestas
del bot. El problema actual es que `_memory_context` retorna `None` cuando no
hay sesión de identidad activa.

## Decisiones

- En `services/orchestrator/orchestrator/domain.py`, conservar `_memory_context`
  para la sesión autenticada y añadir un helper específico para el modo
  conversacional que solo cuando `identity_login_required=false` y no haya
  sesión lea `repository.last_messages` del mismo `contact.id` y los transforme
  a `PromptContext.history`. El flujo de identidad con login requerido conserva
  su bloqueo previo al fallback, sin rutas de herramientas en `AWAITING_LOGIN`.
- `last_messages` devuelve el mensaje entrante ya persistido. Leer hasta
  `MEMORY_CONTEXT_MESSAGES + 1` filas recientes y retirar la última solo si
  `role == "user"`, el texto coincide con `ctx.text` y `at == ctx.received_at`;
  esto identifica el mensaje actual sin depender del reloj de procesamiento.
- Tomar como máximo `MEMORY_CONTEXT_MESSAGES`; no introducir una variable ni
  almacenamiento distintos para este caso.
- Ejecutar ese helper únicamente dentro del flujo consentido existente. Cuando
  la política de consentimiento está activa, los mensajes previos al
  consentimiento no entran al historial persistido elegible.
- Mantener `MEMORY_ENABLED` como interruptor global de historial/memoria. No
  cambiar su default de `Settings` (`false`) ni el valor `true` documentado en
  `.env.example` para el despliegue: el primero es el fallback seguro del
  código y el segundo refleja la configuración de despliegue ya decidida.
- No cambiar el comportamiento RAG ni los permisos de datos del cliente.

## Archivos

- `services/orchestrator/orchestrator/domain.py`
- `services/orchestrator/orchestrator/config.py`
- `.env.example` solo si requiere aclarar comentarios.
- Tests existentes/nuevos en `services/orchestrator/tests/`.

## Alternativas descartadas

- Crear una tabla o base de datos para memoria casual: innecesario porque los
  mensajes ya están persistidos y sujetos a la política de privacidad existente.
- Enviar todo el historial: contradice los límites de contexto configurados y
  aumenta exposición y costo.
- Ampliar el fallback a `AWAITING_LOGIN` o evadir `_apply_identity_rules`:
  cambiaría la política de acceso y podría exponer herramientas personales;
  no es necesario para el despliegue con login opcional.

## Supuestos a confirmar

- Se aplica la decisión vigente en `docs/proyecto.md`: el consentimiento del
  canal gobierna el tratamiento. No se recupera ni envía historial cuando la
  ruta de consentimiento no ha habilitado el procesamiento.
- El límite del contexto casual se toma de `MEMORY_CONTEXT_MESSAGES` (default
  6). La memoria solo funciona donde `MEMORY_ENABLED` está activado.
- La feature no cambia `IDENTITY_LOGIN_REQUIRED` ni habilita modo conversacional
  antes del login cuando esa política está activa.
- No se cambia el plazo general de retención ni la política legal pendiente.

## Dependencias

Ninguna.
