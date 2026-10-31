# Chatbot Lázaro Software: resumen del proyecto y decisiones

> Preparado el 30 de octubre de 2026. Combina las especificaciones del chatbot
> (30 oct 2026, Alejandro) con el trabajo de búsqueda y análisis de
> repositorios, diseño y preparación del harness.
>
> **Nota del arnés:** este documento es el contexto de negocio para los
> agentes. Donde dice OpenCode, el equipo pasó después a **Claude Code**. Los
> cambios de la sección 9 ya están aplicados en este repositorio. Las reglas
> técnicas obligatorias están en `docs/architecture.md` y
> `docs/conventions.md`; si algo de aquí choca con ellas, mandan ellas.

## 1. Resumen ejecutivo

El proyecto es un chatbot de atención y soporte por Telegram, con un panel de
administración y un panel para asesores, hecho con microservicios. Debe
responder preguntas sobre manuales (RAG), distinguir a qué servicio técnico
corresponde una consulta, consultar la base de datos en lenguaje natural y
pasar la conversación a un asesor humano cuando no pueda resolver. El plazo es
de 15 días con un equipo de 4 personas, donde no todos trabajan en el proyecto.

Buscamos repositorios de código abierto que sirvieran de base. Ninguno cubre el
documento completo. La decisión central es:

- Construir un sistema mínimo propio (Telegram, orquestador, RAG con pgvector,
  traspaso a asesor).
- Usar los repositorios solo como referencia, y copiar código únicamente cuando
  su licencia lo permita (el principal es rag-support-bot, con licencia MIT).
- Hacer propia la consulta a la base de datos, con la seguridad impuesta por
  PostgreSQL.
- Trabajar con el harness de desarrollo guiado por especificaciones (SDD),
  empezando en modo supervisado.

## 2. Qué pide el documento de especificaciones

### Alcance y arquitectura

- **Canal:** Telegram. WhatsApp queda fuera por ahora; el canal será una capa
  aparte para poder agregar otros después sin tocar el orquestador.
- **Arquitectura:** microservicios, para cambiar una pieza sin dañar las demás.
  Todo corre con Docker y se organiza en un monorepo con una carpeta por
  servicio y ramas por integrante.
- **Despliegue:** GitHub Actions al hacer commit a la rama principal. Hosting
  de pruebas en Render.
- **Guía técnica:** recomendaciones del ingeniero de la charla del 28 de
  octubre (orquestador propio, ciclo pensar-actuar-reflexionar, agrupar
  mensajes con un worker y caché, contacto como entidad principal, memoria,
  casos, registro de eventos, clasificador pequeño, MCP, modelos baratos en
  pruebas).

### Capacidades del agente

1. **Preguntas sobre manuales (RAG).** El administrador sube manuales (PDF y
   Word como supuesto). Se dividen en fragmentos, se convierten en vectores y
   se busca por significado. Solo se usan fragmentos que superen un umbral de
   similitud; si ninguno lo supera, el agente pasa a un asesor y no inventa. El
   administrador puede revisar, editar, desactivar o añadir fragmentos.
2. **Clasificación del tipo de pregunta.** Las categorías las configura el
   administrador. Un clasificador pequeño devuelve un porcentaje por opción; si
   la confianza es baja, queda como "sin clasificar".
3. **Base de datos en lenguaje natural.** Solo para personal autorizado, con
   usuario de solo lectura, tablas permitidas y registro de cada consulta.
4. **Paso a un asesor.** Un servicio aparte avisa a los asesores (unos 3) y
   registra a quién avisó y por qué. Si ninguno se conecta dentro de un tiempo
   de espera (por definir), el bot avisa al cliente.

### Roles y verificación

| Rol           | Dónde entra                   | Qué puede hacer                                                                  |
|---------------|-------------------------------|----------------------------------------------------------------------------------|
| Administrador | Panel de administración       | Perfiles y roles, manuales, fragmentos, registros del agente                     |
| Asesor        | Panel de servicio al cliente  | Ver conversaciones, historial, tipo de pregunta, responder por Telegram y cerrar el caso |
| Cliente       | Telegram                      | Preguntar sobre manuales y pedir hablar con una persona                          |

En Telegram escriben clientes y personal por el mismo bot, y el perfil
verificado define qué puede preguntar cada uno. La verificación usa un enlace
que une la cuenta de Telegram con un perfil de usuario y contraseña. Riesgo
señalado en el documento: un cliente verificado no debe poder hacer consultas a
la base de datos.

### Restricciones de infraestructura

- La base Postgres gratuita de Render tiene 1 GB, expira a los 30 días, no
  tiene copias de seguridad y solo se permite una por espacio de trabajo.
- El plan gratuito de Render se apaga sin tráfico y tarda cerca de 2 minutos en
  responder de nuevo.
- Costos de modelos: según el ingeniero, unos 20.000 COP de crédito alcanzan
  para bastantes pruebas.

## 3. Qué hicimos

1. Búsqueda de repositorios de GitHub para cada pieza del proyecto.
2. Verificación en código de los candidatos (licencia, actividad, Telegram,
   MCP, fragmentos, requisitos), sin modificar ni levantar nada.
3. Comparación de Helpdock y TGO, y revisión de otros candidatos.
4. Análisis de seguridad de pgmcp para la consulta a la base de datos.
5. Diseño del acceso a la base de datos y de los contratos entre servicios.
6. Revisión del harness SDD que se usará para desarrollar.

Regla de trabajo: lo confirmado en el código se tiene por verificado; lo que
solo salió de un README o de una búsqueda se tiene por no verificado.

## 4. Repositorios evaluados

### Revisados en el código

| Repositorio      | Licencia               | Hallazgos | Veredicto |
|------------------|------------------------|-----------|-----------|
| Helpdock v1.0.0  | AGPL-3.0               | Telegram, RAG con PDF/DOCX, traspaso a asesor y panel. Sin MCP (guardia no-tools). Trata a todos como clientes. Solo muestra cuántos fragmentos hay. Pide 2 vCPU y 4 GB | Descartado como base: la AGPL obliga a publicar un sistema modificado ofrecido por red, y le faltan las partes más delicadas |
| TGO              | Apache 2.0 modificada  | Microservicios en Python, Telegram, MCP, traspaso. El botón de editar fragmentos no hace nada. 0 commits en 3 meses, ~17 contenedores, 4 núcleos y 8 GB | Descartado. Útil como referencia de cómo conecta MCP |
| pgmcp            | Apache 2.0             | MCP en Go para PostgreSQL. Sin lista de tablas, filas máximas sin usar, no guarda el SQL, usuario "unknown", bloquea LEFT JOIN o más de 2 JOIN, envía el esquema completo a OpenAI | Descartado como servicio. Se reutiliza solo el patrón: bloquear palabras de escritura y transacción de solo lectura |
| rag-support-bot  | MIT                    | Telegram, enrutador semántico de 4 categorías sin porcentaje, barrera contra alucinaciones con validación de citas, evaluación de 33 preguntas. 78 pruebas pasan. Solo Markdown, Chroma, sin historial ni traspaso | **Fuente de piezas:** validación de citas y números, formato JSON con chunk_id y cita textual, herramienta de evaluación |

### Revisados solo por licencia y actividad

| Repositorio                    | Licencia                    | Uso |
|--------------------------------|-----------------------------|-----|
| Clean1ines/crm_bot             | Sin licencia                | Solo referencia de ideas (no copiar código) |
| 0xrezan/customer-support-rag   | MIT                         | Pendiente de revisar con cautela |
| anaerobia/dbchatbot            | Sin licencia                | Solo referencia de seguridad de consultas |
| BarziBahadin/NURA              | Sin licencia                | Solo referencia (motivos de traspaso) |
| LuShadowX/ai-support-agent     | Sin licencia                | Solo referencia |
| logfab-stack/agentic-rag       | README dice MIT, sin archivo | Poco confiable |

Sin archivo de licencia no hay permiso legal para copiar el código; sí se puede
aprender de su estructura. Descartados o sin verificar: wh1texdg/support-ai (ya
no accesible), huabeitech/agent-desk (Go + MySQL, sin Telegram, no revisado) y
otros no confirmados.

## 5. Decisiones tomadas

| #  | Decisión | Motivo |
|----|----------|--------|
| D1 | Construir un sistema mínimo propio: Telegram, orquestador, RAG con pgvector y traspaso a asesor | Ningún repositorio cubre el documento; los que se acercan tienen licencias o riesgos que no conviene asumir |
| D2 | Usar los repositorios como referencia; copiar código solo con licencia clara | Sin licencia no hay permiso de copia. rag-support-bot (MIT) es la fuente principal |
| D3 | Descartar Helpdock, TGO y support-ai; pgmcp solo como patrón | Ver sección 4 |
| D4 | Hacer propia la consulta a la base de datos | pgmcp no permite auditoría, lista de tablas ni control del SQL |
| D5 | Definir los contratos entre servicios antes de programar | Permite trabajar en paralelo sin romperse |
| D6 | Desarrollar con el harness SDD, empezando en modo supervisado | El humano aprueba cada spec; el modo nocturno bloquea pip, gasta muchas llamadas al modelo y se salta la aprobación |
| D7 | Se puede pagar una segunda base de datos | Quita el límite de una base gratuita por espacio de trabajo y resuelve vencimiento y copias |

## 6. Diseño de la consulta a la base de datos (feature posterior)

La seguridad no depende solo del código: la impone PostgreSQL.

1. Usuario de solo lectura con `GRANT SELECT` solo sobre un esquema de vistas
   (esa es la lista de tablas permitidas). `default_transaction_read_only` y
   `statement_timeout` se configuran por rol, pero una sesión puede cambiarlos
   con `SET`, así que la barrera real son los permisos mínimos.
2. Transacción de solo lectura explícita en cada consulta, con tiempo máximo y
   límite de filas.
3. Validación del SQL: una sola sentencia y solo `SELECT`.
4. Auditoría con otra conexión: la escribe el orquestador con su usuario normal
   de aplicación, nunca el usuario de lectura. Guarda el SQL ejecutado, quién
   lo pidió y cuántas filas devolvió.
5. Consultas predefinidas con parámetros (p. ej. `consultar_pedido(numero)`)
   para lo conocido; el SQL libre sobre vistas queda solo para el personal.
6. Acceso solo para personal verificado. La identidad de quien pregunta viaja
   en cada petición y se registra en la auditoría. Si algún día un cliente ve
   sus propios datos, se impone con RLS o vistas filtradas.

**Pruebas obligatorias:** un cliente no puede consultar la base de datos, y
ningún usuario logra que el sistema ejecute código que él escribió.

## 7. Contratos entre servicios (borrador de la versión mínima)

Cada servicio habla con los demás por HTTP y JSON.

| De → a                  | Ruta                     | Envía                                                   | Devuelve |
|-------------------------|--------------------------|---------------------------------------------------------|----------|
| Telegram → orquestador  | `POST /messages`         | update_id, telegram_user_id, chat_id, text, received_at | 202 Accepted (descarta update_id repetidos) |
| Orquestador → Telegram  | `POST /send`             | chat_id, text                                           | `{sent: true}` |
| Orquestador → RAG       | `POST /search`           | query, top_k, category (opcional)                       | lista de `{chunk_id, manual, text, score}` |
| Orquestador → handover  | `POST /handover`         | case_id, contact_id, reason, last_messages              | `{status: "notified" o "no_advisors"}` |
| Asesor → orquestador    | `POST /cases/{id}/reply` | advisor_id, text                                        | `{sent: true}` |
| Script de carga → RAG   | `POST /manuals`          | archivo, nombre                                         | `{manual_id, chunks}` |

Reglas comunes: token de servicio en el encabezado, errores como
`{error, message}` e identificador único por mensaje para descartar repetidos.

## 8. Versión mínima y orden de trabajo

La versión mínima es: canal Telegram, orquestador, RAG con manuales (cargados
por un script mientras no exista el panel) y traspaso. Después vienen la
consulta a la base de datos y los paneles.

Features del harness (ver `feature_list.json`):

1. Contratos entre servicios
2. Esqueleto de servicios con Docker (Postgres con pgvector y Redis)
3. Telegram gateway (recibir, descartar repetidos, enviar)
4. Orquestador básico
5. RAG: ingesta de manuales y búsqueda con umbral
6. No inventar: validación de citas y rechazo fijo
7. Traspaso a asesor
8. Evaluación con preguntas de ejemplo

**Quedan para después:** consulta a la base de datos, paneles, clasificador,
edición de fragmentos y verificación de cuentas (enlace Telegram ↔ perfil).

## 10. Cambios propuestos al documento original (pendientes de confirmar)

- **Un bot o dos.** Alternativa más segura: un bot para clientes (RAG y
  traspaso) y otro para personal (consulta a la base de datos).
- **Datos propios del cliente.** No está en el documento; sería funcionalidad nueva.
- **Clasificador.** Una llamada barata al modelo con la lista de categorías, o
  un clasificador por similitud (habría que reescribir el de rag-support-bot).
- **Edición de fragmentos.** Ningún repositorio la resuelve bien; hay que construirla.

## 11. Riesgos principales

| Riesgo | Mitigación |
|--------|------------|
| Un cliente consulta la base de datos | Acceso solo a personal verificado, usuario de solo lectura, pruebas obligatorias |
| Inyección de instrucciones desde manuales o mensajes | Tratar el texto como datos; el modelo no tiene herramientas que escriban en la base |
| Datos personales (Ley 1581, sin verificar con abogado) | Guardar lo mínimo, aviso y autorización antes de producción, poder borrar datos |
| La base gratuita de Render expira y no tiene copias | Plan de pago o exportar periódicamente |
| Render gratuito tarda en despertar y Telegram reenvía mensajes | Guardar update_id y descartar repetidos |
| Claves filtradas o leídas por agentes | `.env` fuera del repositorio y bloqueado para lectura de agentes |
| Equipo reducido y principiante en programación | Alcance mínimo, specs revisados por humanos, contratos primero |
| Licencias | Copiar código solo con licencia clara y conservar los avisos (MIT y Apache 2.0) |

## 12. Dudas abiertas

Del documento original:

- Qué manuales hay: cantidad, formatos y tamaño real.
- Quién crea los usuarios y contraseñas de los clientes en Telegram.
- Qué son los "servicios técnicos" (las categorías serán configurables).
- Cuánto espera el bot a un asesor antes de avisar que no hay asesores.
- Si se procesan audio e imágenes en esta etapa.
- Si se implementan los botones de PQRS (propuesta: fuera de la versión mínima).
- Datos personales: aviso y autorización según la Ley 1581.
- Quién paga la API del proveedor de IA en producción.
- Qué pasa con los fragmentos corregidos a mano si se vuelve a subir un manual.

Nuevas, surgidas del análisis:

- Si se acepta separar el bot de clientes y el de personal.
- Si el empresario acepta que el esquema de la base de datos se envíe al proveedor de IA.
- Modelo de embeddings y umbral de similitud (calibrar con un manual real).
- Si la herramienta de consultas necesita aceptar varios JOIN.

> **Regla para los agentes:** una duda abierta NO se resuelve inventando. Si
> una feature depende de una de ellas, el spec la recoge como **supuesto
> configurable** (valor por defecto + variable de entorno) en la sección
> «Supuestos a confirmar» de `design.md`, o la feature queda `blocked`.
