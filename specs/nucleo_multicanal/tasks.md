# Tasks — nucleo_multicanal (feature #36)

- [x] T1 — Añadir modelos compartidos para mensaje normalizado, capacidades y
  bloques abstractos; exportarlos desde `lazaro_contracts`. Cubre: R1, R2.
- [x] T2 — Actualizar `contracts/CONTRATOS.md`, ejemplos y pruebas para los
  modelos/contratos multicanal, manteniendo validación de payload Telegram
  existente. Cubre: R1, R2, R3.
- [x] T3 — Implementar la interfaz común de adaptador y `FakeWhatsAppAdapter`
  inyectable con capacidades, ventanas, plantillas aprobadas y errores
  simulables; normalizar también estados de entrega. Cubre: R4, R7, R9, R12.
- [x] T4 — Adaptar Telegram para normalizar updates y representar los bloques
  abstractos compatibles sin alterar los envíos legacy. Cubre: R1, R2, R3.
- [x] T5 — Cambiar las claves de deduplicación Redis y del repositorio del
  orquestador a `(channel, external_message_id)` y mantener idempotencia ante
  concurrencia/reintentos. Cubre: R5, R6.
- [x] T6 — Aplicar control de capacidad antes del envío: texto libre denegado
  fuera de la ventana WhatsApp y plantilla permitida solo si está aprobada.
  Cubre: R7, R8, R9.
- [x] T7 — Añadir tests con adaptadores falsos para normalización, bloques,
  equivalencia Telegram/WhatsApp, colisión de IDs entre canales, duplicados del
  mismo canal, ventana/plantillas, estados de entrega y fallos de envío; asegurar
  que no se requiere red ni credenciales. Cubre: R1, R2, R3, R4, R5, R6, R7,
  R8, R9, R10, R11, R12.
- [x] T8 — Ejecutar `./init.sh` y confirmar que los flujos Telegram previos y
  los nuevos casos quedan verdes; registrar la trazabilidad requirement-test.
  Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12.
  (La ejecución de `./init.sh` la realiza Claude al cerrar la sesión; no se
  marca hasta obtener la suite verde.)
- [x] T9 — Extender `Contact` y la migración de `contacts` con `channel`,
  `external_user_id` y `external_chat_id`; preservar IDs/relaciones de Telegram
  histórico en un backfill repetible y permitir contactos WhatsApp sin campos
  ID legacy. Cubre: R13, R14, R16, R17.
- [x] T10 — Generalizar Postgres/FakeRepository para buscar y crear contactos
  por pareja de canal e ID externo solo después del consentimiento vigente;
  antes, resolver la pareja en memoria, no crear contacto y limitar escrituras a
  `privacy_consents`, sujeto a la excepción de deduplicación técnica heredada de
  T5. Conservar wrappers legacy Telegram. Cubre: R13, R14, R16, R21, R22, R23.
- [x] T11 — Generalizar almacenamiento y consultas de consentimiento con la
  pareja de identidad; migrar las filas Telegram existentes con versión, hash y
  fecha intactas incluso al repetir la migración; permitir filas WhatsApp sin ID
  Telegram. Cubre: R15, R18.
- [x] T12 — Mantener `client_id` ausente en los mensajes/contactos creados por
  esta feature y comprobar que no se vinculan identidades de canales; dejar el
  enlace autenticado para #38. Cubre: R19.
- [x] T13 — En `test_multichannel_identity.py`, probar que el lookup tras
  consentimiento usa `(channel, external_user_id)` y que antes de consentir no
  persiste contacto; verificar que Telegram legacy solo conserva `update_id` en
  `processed_updates`, que los requests canónicos/nuevos canales y privacidad
  desconfigurada no escriben deduplicación persistente, y que no se inserta
  `processed_messages` antes del consentimiento. En `test_repository_schema.py`,
  ejecutar más de una vez los backfills y demostrar idempotencia conservando
  IDs/relaciones de contacto y evidencia histórica. Cubrir también IDs numéricos
  coincidentes, consentimientos independientes, ausencia de uso WhatsApp de
  `telegram_user_id` y no vínculo antes de login. Cubre: R13, R14, R15, R16, R17,
  R18, R19, R20, R21, R22, R23.
- [x] T14 — Ejecutar `./init.sh` después de la migración y las pruebas nuevas;
  confirmar que #35 y los flujos legacy Telegram siguen verdes y registrar la
  trazabilidad requirement-test. Cubre: R13, R14, R15, R16, R17, R18, R19,
  R20, R21, R22, R23.
  Verificado: `./init.sh` pasó (2243 passed, 1 skipped, 1 warning).
