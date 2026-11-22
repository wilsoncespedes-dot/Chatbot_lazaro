> **PLAN DESCARTADO (2026-11-21).** El usuario cambió la prioridad: ya no se
> harán canales nuevos ni specs de la retroalimentación. El trabajo actual es
> `progress/plan_respuestas.md` (el bot debe responder bien sin salirse de su
> rol). Este archivo se conserva solo como registro histórico.

# Plan — specs derivadas de `LEER-ESTE.txt`

> Objetivo: convertir el feedback del profesor en specs SDD ejecutables, sin
> duplicar lo ya implementado y sin presentar como hecho lo que él marcó como
> «posibilidad». Estado de partida: 58 features `done`, ninguna en curso.

## 0. Reglas que mandan el plan

- **Una feature a la vez** (`AGENTS.md` §3). No mezclar canales con gráficos en
  la misma sesión.
- **Contratos primero** (`docs/architecture.md` §3.2): cualquier canal nuevo
  pasa antes por una feature de contrato.
- **EARS estricto** en `requirements.md`, con un test concreto por `R<n>`
  (`docs/specs.md`, `CHECKPOINTS.md` C6).
- **No inventar decisiones de producto** (`docs/proyecto.md` §12): las dudas se
  escriben como «Supuestos a confirmar» en `design.md` o se elevan como gate.
- `LEER-ESTE.txt` §23-34 y §182-195: la API de Lázaro (clientes, bots por ID,
  datos de hoteles/restaurantes) **solo se menciona como posibilidad**. No se
  escribe código ni se promete fecha.

## 1. Mapa de lo que dijo el profe contra lo que ya existe

| Punto del profe | Estado real en el repo | Acción del plan |
|---|---|---|
| Bandeja única con mensajes de todos los canales y respuesta por el mismo canal | Parcial: núcleo multicanal Telegram + WhatsApp (#36, #43) y bandeja con etiqueta de canal (#41) | Extender canales (Fase B/C) |
| «Multicanal de verdad», no solo dos plataformas | Solo dos canales hoy | Fase B/C, con Instagram y Facebook primero |
| Varios asesores atendiendo conversaciones de distintos lugares | Hecho: #29, #41, #49, #52, #53 | Solo documentarlo; no rehacerlo |
| Bots responden primero, asesores revisan y entran cuando hace falta | Hecho: #32, #39, #41, #52 | Ajuste de intención comercial (Fase D) |
| Bot resuelve lo simple (enviar panel/QR sin asesor) | No existe | Fase D |
| Consulta a la BD en lenguaje natural | Hecho (#26) y con herramientas por estado (#39) | No reintroducir MCP: la decisión D4 la resolvió propia. Solo aclararlo en docs |
| Pasar datos a librería de gráficos | No existe; el profe dudó del tiempo | Fase F, opcional, al final |
| Saber qué canales hay y cómo llegar; aceptar términos una sola vez | Consentimiento versionado (#37, #46); falta una pantalla de canales disponibles | Incluido en Fase A/C |
| Sin registro ni login; copiar/pegar ID de usuario | **Choca con #38** (login web con credenciales, decisión vigente §13.3) | Gate G2; no cambiar en silencio |
| Conectar la sección de clientes a la API de Lázaro | No hay acceso a esa API; el profe lo marcó como posibilidad | Fase A: texto explícito de «posibilidad futura», sin código |

## 2. Gates a confirmar antes de redactar cada spec

| Gate | Pregunta | Default recomendado (se aplica si no hay respuesta) |
|---|---|---|
| G1 | ¿Qué canales nuevos se implementan ya? | Instagram y Facebook Messenger (Meta Graph, reutiliza la firma `X-Hub-Signature-256` ya usada por WhatsApp). SMS y TikTok quedan como posibilidades: TikTok tiene chat dudoso según el propio profe |
| G2 | ¿Se mantiene el login de #38 o se pasa a ID copiado y pegado? | Mantener #38. Añadir un ID de cliente copiable y documentar el flujo sin login como alternativa a validar con Lázaro, no como cambio de comportamiento |
| G3 | ¿Se hace la parte de gráficos en esta entrega? | No: queda como posibilidad documentada y feature opcional #63, se ejecuta solo si sobra tiempo |
| G4 | ¿Se promete la integración con la API de Lázaro? | No, bajo ninguna forma. Solo `README`/presentación con lenguaje de posibilidad |
| G5 | ¿Se cambia la consulta a BD por un MCP? | No. D4 + #26 son la decisión vigente: vistas con RLS, allowlist, herramientas autorizadas en `harness.py` |

Estos gates no bloquean la Fase A ni la Fase B. G1 bloquea la Fase C, G2 bloquea
la Fase G y G3 bloquea la Fase F.

## 3. Orden de ejecución

### Fase A (opcional) — Alineación del discurso (sin SDD, sin código)

**No es necesaria para el código ni para los tests.** Comprobado el 2026-11-21:
`README.md` describe con exactitud lo que existe (Telegram y WhatsApp), no
menciona la API de Lázaro como integrada y en el repo no hay archivo de
presentación. No hay ninguna afirmación falsa que corregir. El comentario del
profesor sobre «mejorar la comunicación» apunta a la exposición oral, que vive
fuera de este repositorio.

Se ejecuta solo si va a haber presentación y se quiere cubrir el «por exceso» que
recomendó el profe. Versión mínima (20-30 min): un párrafo en el README y una
diapositiva con tres bloques — «ya funciona», «en evaluación», «posibilidades
futuras» —; no reescribir el README completo.

Tarea de documentación permitida por `docs/specs.md` («Cuándo NO aplica SDD»).

- Revisar `README.md` y la presentación: destacar bandeja única, etiqueta por
  canal, bots + asesores humanos, y consulta a datos ya implementada.
- Añadir una sección `Posibilidades a futuro` con: API de Lázaro para clientes
  y datos de hoteles/restaurantes, búsqueda de clientes por ID, gráficos y
  canales adicionales. Redacción obligatoria: «se podría conectar…», nunca
  «ya está» ni «lo vamos a implementar».
- Aclarar que la consulta en lenguaje natural existe con acceso propio y
  seguro (`docs/consulta_bd.md`), no con un MCP nuevo.
- Verificación: grep de frases prohibidas (`ya integrado`, `integración
  completa con Lázaro`, `próximamente implementado`) da cero resultados.

### Fase B — `#59 contrato_multicanal_extendido` (spec de contrato)

- `name`: `contrato_multicanal_extendido`, `title`: «Contrato: canales adicionales».
- Alcance: extender el `Literal` de `Channel` en
  `contracts/lazaro_contracts/channels.py` y documentar las rutas en
  `contracts/CONTRATOS.md`. Sin lógica de adaptadores.
- Acceptance: nuevos valores de canal aceptados por los modelos compartidos;
  Telegram y WhatsApp siguen válidos; un canal no listado se rechaza con error
  de validación; request/response de envío traducen al canal correcto.
- Esqueleto EARS (a desarrollar en `requirements.md`):
  - `R1` CUANDO un modelo de contrato recibe `channel` con un valor de la lista
    ampliada, DEBE aceptarlo.
  - `R2` SI `channel` no pertenece a la lista, ENTONCES el modelo DEBE rechazarlo
    con error de validación.
  - `R3` El contrato DEBE conservar los valores `telegram` y `whatsapp` sin
    cambios de forma.
- Design: sin dependencias nuevas; sin supuestos nuevos salvo G1.
- Tests: `contracts/tests/` (modelos) + comprobación de que los tests actuales
  de `channels.py` siguen verdes.

### Fase C — `#60 adaptadores_instagram_facebook` (depende de #59 y G1)

- `name`: `adaptadores_instagram_facebook`, `title`: «Adaptadores de Instagram y Facebook Messenger».
- Alcance: webhooks entrantes y envío saliente en
  `services/telegram_gateway/`, detrás de la interfaz `ChannelAdapter`;
  verificación de firma Meta y normalización a `NormalizedMessage`.
- Acceptance: mensaje de Instagram/Facebook llega a la bandeja con su etiqueta;
  la respuesta del asesor sale por el mismo canal; idempotencia por
  `(canal, mensaje_externo_id)`; firma inválida → `401`; sin token de servicio →
  `401` en rutas internas.
- Esqueleto EARS:
  - `R1` CUANDO llega un webhook firmado de Instagram, el gateway DEBE enviar un
    `NormalizedMessage` con `channel="instagram"` al orquestador.
  - `R2` CUANDO un asesor responde un caso de Facebook, el gateway DEBE publicar
    la respuesta en Facebook y no en otro canal.
  - `R3` SI la firma del webhook es inválida ENTONCES el gateway DEBE responder
    `401` sin reenviar el mensaje.
  - `R4` CUANDO llega un `mensaje_externo_id` ya visto en el mismo canal, el
    gateway DEBE descartarlo sin reenviarlo.
- Design: reutilizar el verificador de firma de `whatsapp_cloud.py`; sin SDK
  nuevo si basta con `httpx`; variables nuevas en `.env.example`
  (`META_PAGE_ACCESS_TOKEN`, `META_APP_SECRET`, etc.). Supuestos: permisos de la
  página de Facebook y aprobación de Meta para Messenger/Instagram.
- Tests: `services/telegram_gateway/tests/test_instagram_webhook.py`,
  `test_facebook_send.py`, fakes de `httpx`, sin red real.

### Fase D — Intención comercial y bot de tareas simples

- `#61 intencion_comercial`: añadir `me interesa` y variantes a
  `HANDOVER_KEYWORDS` (y a la lista administrable si aplica), con test de que
  esa frase dispara `escalar_a_asesor` y de que no dispara con frases negativas.
  Reutiliza `is_handover_request`; no crear un clasificador nuevo.
- `#62 bot_tareas_simples`: el bot entrega el enlace al panel/QR sin intervención
  del asesor, solo para perfil autenticado y con consentimiento vigente.
  Diseño: nueva herramienta en `TOOL_MATRIX` con permisos por estado, texto
  administrable en el panel, sin exponer secretos en el QR.
  Riesgo: un QR que contenga un token de sesión sería un secret filtrado; el
  diseño debe usar un enlace público o un token de un solo uso.

### Fase F (opcional) — `#63 visualizacion_graficos`

- Solo si G3 lo autoriza y después de #26.
- Renderizado en el servidor (SVG propio, mismo origen, sin CDN para no romper
  la CSP de #56). Dependencia nueva solo si se justifica licenciaMIT/BSD/Apache.
- Acceptance: el bot puede acompañar la respuesta de una consulta autorizada con
  una tabla/gráfico generado desde el mismo `dataset` ya auditado; nunca
  inserta SQL nueva ni datos de otro cliente.

### Fase G (condicionada por G2) — `#64 flujo_identificador_cliente`

- Solo si el dueño decide abandonar el login de #38.
- Si no se aprueba: no existe esta feature. En su lugar, Fase A añade un ID
  copiable al panel como ayuda al asesor, sin cambio de autenticación.

## 4. Cómo se ejecuta cada feature

1. `spec_author` crea `specs/<name>/{requirements,design,tasks}.md` y marca el
   feature como `spec_ready` en `feature_list.json`.
2. `reviewer` revisa una sola pasada: aceptación, coherencia, dependencias y
   decisiones ya tomadas. Si aprueba → `in_progress`.
3. `implementer` ejecuta `tasks.md` en orden, marca `[x]` y escribe
   `progress/impl_<name>.md` con la trazabilidad `R<n>` → test.
4. `reviewer` verifica trazabilidad y `./init.sh` en verde → `done`; se mueve el
   resumen a `progress/history.md` y se vacía `progress/current.md`.
5. Repetir con la siguiente feature. Nunca dos en `in_progress`.

## 5. Entregables de este plan

- `progress/plan_profe.md` — este documento.
- `README.md` / material de presentación — Fase A.
- `feature_list.json` — nuevos IDs `#59` a `#64`, en `pending` hasta que el
  `spec_author` correspondiente los pase a `spec_ready`.
- `specs/<name>/` — un carpeta por feature, solo cuando se abra esa feature.
- `contracts/CONTRATOS.md` y `contracts/lazaro_contracts/channels.py` — Fase B.
- `services/telegram_gateway/` y sus tests — Fase C.
- `services/orchestrator/` y sus tests — Fase D (y F/G si procede).

## 6. Criterio de éxito

- Ninguna frase que prometa la API de Lázaro como implementada (hoy ya se
  cumple: el README no la menciona; solo hay que vigilarlo si se escribe una
  presentación).
- Todo lo que el profe marcó como prioritario está cubierto por una feature
  `done` con tests, o por una decisión documentada de por qué no se hace.
- `./init.sh` en verde al cierre de cada feature.
