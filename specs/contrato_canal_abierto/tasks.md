# Tasks — #60 `contrato_canal_abierto`

Reglas para todas las tasks: solo se tocan los archivos de la tabla de
`design.md`; no se edita ni se borra ningún test ni ejemplo existente (R47);
cada test nuevo lleva en su docstring el `R<n>` que cubre; sin dependencias
nuevas. No se adelanta trabajo de #61, #62 ni #65.

## Contrato (`contracts/lazaro_contracts`)

- [x] T1 — En `common.py`: añadir `LAZARO_TIMESTAMP_HEADER`, `LAZARO_SIGNATURE_HEADER` y `DEFAULT_SIGNATURE_WINDOW_SECONDS` con los valores de `design.md`. Cubre: R27.
- [x] T2 — En `channels.py`: añadir `CHANNEL_ID_PATTERN`, `MIN_CHANNEL_ID_LENGTH`, `MAX_CHANNEL_ID_LENGTH` y redefinir `Channel` como slug (`StringConstraints` con patrón y longitud). Cubre: R1, R2.
- [x] T3 — En `channels.py`: añadir las constantes de límites, `MIME_TYPE_PATTERN`, `_check_https_url`, `HttpsUrl`, `_check_attachment_name`, `AttachmentKind` y `Attachment` según `design.md`. Cubre: R9, R10, R11, R12, R13, R14, R48.
- [x] T4 — En `channels.py`: ampliar `MessageKind`, añadir `MessageDirection`, `_json_depth` (iterativo) y `_check_metadata`; añadir a `NormalizedMessage` `direction`, `attachments` y `metadata` con `exclude_if`, y ampliar `_content_matches_kind` en el orden de `design.md`. Cubre: R3, R4, R5, R6, R7, R8, R15, R16, R17, R18, R19, R20, R24, R25, R26.
- [x] T5 — En `channels.py`: añadir a `ChannelCapabilities` `supports_buttons=True`, `supports_images=False`, `supports_files=False`, `supports_audio=False`. Cubre: R21.
- [x] T6 — En `channels.py`: añadir `ImageBlock` e incluirlo en la unión discriminada `ResponseBlock` (sin tocar el conteo de enlaces). Cubre: R22, R23.
- [x] T7 — En `__init__.py`: importar y añadir a `__all__` todos los nombres de R27. Cubre: R27.

## Tests del contrato

- [x] T8 — Crear `contracts/tests/test_canal_abierto.py` con:
  `test_channel_accepts_valid_slugs` (parametrizado con los valores de R1, en `NormalizedMessage` y `ChannelSendRequest`) — R1;
  `test_channel_rejects_invalid_slugs` (`""`, `"t"`, 33 caracteres, `"Telegram"`, `"tele gram"`, `"-tg"`, `"tg-"`, `"tg--x"`, `"tg_-x"`, `"1canal"`, `"canal.externo"`, `"canal/x"`, `"ñandu"`, `"telegram\n"`, `5`; en ambos modelos) — R2;
  `test_message_kind_has_exactly_six_values` (`typing.get_args(MessageKind)`) y `test_unknown_kind_video_is_rejected` — R3;
  `test_media_kind_requires_attachment` (parametrizado `image`, `file`, `audio`) — R4;
  `test_attachment_type_must_match_kind` — R5;
  `test_non_media_kind_rejects_attachments` (parametrizado `text`, `button`, `unsupported`, con sus campos válidos) — R6;
  `test_media_kind_accepts_optional_caption` (sin `text` y con `text`) — R7;
  `test_attachments_are_limited_to_ten` (10 válido, 11 inválido) — R8;
  `test_attachment_accepts_minimal_and_full_fields` — R9;
  `test_attachment_mime_type_rules` (válidos: `image/jpeg`, `application/pdf`, `audio/ogg; codecs=opus`, tipo `vnd.` largo; inválidos: `jpeg`, `image/`, `/jpeg`, `image jpeg`, `"image/jpeg\n"`, 256 caracteres) — R10;
  `test_attachment_name_rules` (válidos: `"foto ñandú.jpg"`, 255 caracteres; inválidos: `""`, 256 caracteres, `"../x"`, `"a\\b"`, `"a\x00b"`, `"a\nb"`) — R11;
  `test_attachment_size_rules` (válidos 0 y 2 147 483 648; inválidos -1 y 2 147 483 649) — R12;
  `test_https_url_rules` (parametrizado sobre `Attachment.url` e `ImageBlock.url`; válidos: `https://x.example.com/a.jpg`, `HTTPS://x.example.com/a`, exactamente 2048 caracteres; inválidos: `http://x.example.com/a`, `https://`, `ftp://x.example.com`, `javascript:alert(1)`, `https://user:pw@x.example.com/a`, `https://x.example.com/a b`, `"https://x.example.com/a\n"`, 2049 caracteres) — R13, R23;
  `test_attachment_rejects_binary_fields` (`data`, `content`, `bytes`) — R14;
  `test_metadata_defaults_to_empty_object_and_accepts_json` — R15;
  `test_metadata_size_limit` (objeto de exactamente 4096 bytes válido, también con caracteres multibyte; 4097 inválido; tamaño calculado como en `requirements.md`) — R15, R16;
  `test_metadata_depth_limit` (profundidad 5 válida, 6 inválida) — R15, R17;
  `test_metadata_must_be_object` (lista, texto, número y `null`, vía `model_validate_json`) — R18;
  `test_direction_defaults_to_inbound_and_accepts_outbound` (y `"saliente"` inválido) — R19;
  `test_outbound_rejects_button_and_unsupported` (y acepta `text` e `image` salientes) — R20;
  `test_capabilities_new_fields_have_defaults` (sin los campos → `True, False, False, False`; con valores explícitos se respetan) — R21;
  `test_image_block_is_part_of_response_blocks` (`ResponseBlocks` con texto + dos imágenes + un enlace válido; `ChannelSendRequest` con imagen válido) — R22;
  `test_image_block_rejects_missing_or_invalid_fields` (sin `url`, sin `alt_text`, `alt_text` vacío, 1025 caracteres; 1024 válido) — R23;
  `test_historical_payloads_validate_with_defaults` (parametrizado con los cinco ejemplos de R24 leídos de `contracts/examples/`) — R24;
  `test_serialization_omits_default_new_fields` (`model_dump()` y `model_dump_json()` de `normalized_message.json` y `normalized_button_message.json` tienen exactamente las claves históricas) — R25;
  `test_serialization_keeps_non_default_fields_and_round_trips` (con adjunto, `metadata` y `outbound`: claves presentes y `model_validate_json(dump) == original`) — R26;
  `test_new_names_are_exported_with_contract_values` — R27;
  `test_attachment_requires_type_and_mime_type` (adjunto sin `type` y adjunto sin `mime_type`, ambos rechazados con `ValidationError`) — R48.
  Cubre: R1–R27, R48.

## Documento `CONTRATOS.md`

- [x] T9 — En `contracts/CONTRATOS.md`: puntos 1–8 y 10 de la sección «`CONTRATOS.md`» de `design.md` (viñeta de Autenticación, tablas de `NormalizedMessage`, nuevo `### Attachment`, fila `ImageBlock`, tabla de `ChannelCapabilities`, párrafo de la variante canónica, filas 422 de `POST /send` y `POST /messages`, fila `S17`). Cubre: R28, R29, R36, R37, R38.
- [x] T10 — En `contracts/CONTRATOS.md`: añadir la sección `## Canal genérico (webhook firmado)` (punto 9 de `design.md`) con sus subsecciones y los tres bloques de ejemplo copiados byte a byte. Cubre: R30, R31, R32, R33, R34, R35.
- [x] T11 — Crear `contracts/tests/test_canal_abierto_doc.py` con los ayudantes de `design.md` y:
  `test_normalized_message_table_lists_all_fields` y `test_attachment_table_lists_all_fields` — R28;
  `test_response_blocks_table_lists_image_block` y `test_capabilities_table_lists_all_fields_with_defaults` — R29;
  `test_generic_webhook_route_is_documented` (Expone `telegram_gateway`, menciona `#62`, Llama no vacío, Modelos `NormalizedMessage` y `MessageResponse`, `200 OK`, filas 401/404/422/500) — R30;
  `test_generic_section_json_examples_validate` (la sección incluye al menos un ejemplo `inbound` con adjunto y `metadata` y uno `outbound`, y todo bloque `json` y el cuerpo de todo bloque `http` de la sección validan como `NormalizedMessage`) — R31;
  `test_signature_rules_are_documented` (fragmentos de R32) — R32;
  `test_signed_examples_are_verifiable` (dos bloques `http`: firma recalculada igual a la documentada; la ruta de entrada coincide con su `channel`) — R33;
  `test_callback_is_documented` (fragmentos de R34) — R34;
  `test_equivalence_table_maps_assignment_names` (las nueve parejas de R35 y cada campo existe en `NormalizedMessage.model_fields`) — R35;
  `test_authentication_lists_generic_webhook` — R36;
  `test_send_and_messages_document_temporary_rejections` (párrafo de la variante canónica y filas 422 de `POST /send` y `POST /messages`) — R37;
  `test_assumption_s17_documents_limits_and_text_only` (fragmentos: `channel`, `2 a 32`, `10 adjuntos`, `4096 bytes`, `profundidad 5`, `2048`, `1024`, `255`, `2 GiB`, `nunca el binario`, `unsupported_reply`, `422`, `#61`) — R38.
  Cubre: R28–R38.

## Gateway (`services/telegram_gateway`)

- [x] T12 — En `telegram_gateway/domain.py`: añadir `UnknownChannel` y `UnsupportedBlock`, importar `ImageBlock` y añadir en `send_response` la guarda de imagen antes de las comprobaciones de ventana. En `telegram_gateway/main.py`, `send`: resolver `telegram` y `whatsapp` explícitamente y lanzar `UnknownChannel` para cualquier otro canal, antes de la comprobación `adapter is None`. Cubre: R39, R40.
- [x] T13 — Crear `services/telegram_gateway/tests/test_canal_abierto.py` (patrón `make_client` de `tests/test_multicanal.py`) con:
  `test_send_unknown_channel_returns_422_without_sending` (parametrizado `canal-externo`, `instagram`; WhatsApp falso configurado; `telegram.sent == []` y `whatsapp.sent == []`) — R39;
  `test_send_unknown_channel_is_422_even_without_whatsapp` (`whatsapp=None` → `422`, no `502`) — R39;
  `test_send_image_block_is_rejected_on_current_channels` (parametrizado `telegram` y `whatsapp`; solo imagen y texto + imagen; `422 validation_error` y nada enviado) — R40;
  `test_send_response_allows_image_when_capability_is_declared` (adaptador de prueba con `supports_images=True`: `send_response` llama a `send` con el bloque) y `test_send_response_rejects_image_without_capability` (`UnsupportedBlock`) — R40;
  `test_current_adapters_keep_their_capabilities` (`TelegramChannelAdapter(...).capabilities()`, `ChannelCapabilities(**whatsapp_capabilities(window_open=True/False))` porque la función devuelve un `dict`, y `FakeWhatsAppAdapter().capabilities()`) — R41;
  `test_forwarded_payload_has_only_historical_keys` (`monkeypatch` de `httpx.post` en `telegram_gateway.adapters.orchestrator`; `post_message` con un `NormalizedMessage` de texto de `domain.normalize_incoming` (Telegram), uno de botón de `domain.normalize_callback` y uno `unsupported` de `whatsapp_cloud.normalize_message`; las claves del JSON enviado son exactamente las históricas) — R42.
  Cubre: R39, R40, R41, R42.

## Orquestador (`services/orchestrator`)

- [x] T14 — En `orchestrator/domain.py`: añadir `ATTENDED_CHANNELS` con su comentario. En `orchestrator/main.py`, `post_message`: guarda de `design.md` como primera instrucción. Cubre: R43, R44.
- [x] T15 — Crear `services/orchestrator/tests/test_canal_abierto.py` (fixture `env`, patrón de `tests/test_multichannel_identity.py` y `tests/test_conversation_states.py::test_unsupported_content_gets_fixed_reply_without_state_change`) con:
  `test_post_messages_rejects_unattended_channel` (parametrizado `canal-externo`, `instagram`: `422 validation_error`, `processed_messages` sin cambios, nada enviado por el gateway falso) — R43;
  `test_post_messages_rejects_outbound_direction` (canal `whatsapp`, `direction` = `outbound`: mismas comprobaciones) — R44;
  `test_media_kinds_get_unsupported_reply_without_persistence` (parametrizado `image`, `file`, `audio` × `telegram`, `whatsapp`, con adjunto y `metadata`: el último envío es `unsupported_reply` al mismo canal y chat, `repo.messages == []`, estado sin cambios, `rag.calls == []` y `llm.calls == []`) — R45;
  `test_post_messages_accepts_media_kind` (`202` con `status` = `accepted`) — R46.
  Cubre: R43, R44, R45, R46.

## Cierre

- [x] T16 — Ejecutar `python -m pytest contracts`, `python -m pytest services/telegram_gateway`, `python -m pytest services/orchestrator` y `./init.sh`; todo verde. Comprobar con `git status --porcelain -- contracts/tests contracts/examples services/*/tests` que solo aparecen los cuatro archivos de test nuevos como no rastreados o añadidos, sin ninguna línea `M` ni `D`. Cubre: R47.
- [x] T17 — Escribir `progress/impl_contrato_canal_abierto.md` con la trazabilidad `R<n> → archivo::test` de R1–R48 y el resultado de `./init.sh`. Cubre: R1–R48.
