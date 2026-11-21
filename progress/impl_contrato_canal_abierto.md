# Implementación — #60 `contrato_canal_abierto`

Implementadas T1–T17 de `specs/contrato_canal_abierto/tasks.md`: contrato abierto
en `contracts/`, `CONTRATOS.md` con el webhook genérico firmado y guardas
mínimas en gateway y orquestador para conservar el comportamiento actual.

## Cambios

- `contracts/lazaro_contracts/common.py`: cabeceras de firma y ventana por defecto.
- `contracts/lazaro_contracts/channels.py`: `Channel` como slug, `Attachment`,
  `MessageKind` ampliado, `metadata`, `direction`, capacidades nuevas e
  `ImageBlock`.
- `contracts/lazaro_contracts/__init__.py`: exportaciones de R27.
- `contracts/CONTRATOS.md`: tablas de campos, sección «Canal genérico (webhook
  firmado)», filas 422 y supuesto S17.
- `services/telegram_gateway`: `UnknownChannel` y `UnsupportedBlock`, resolución
  explícita de `telegram`/`whatsapp` en `POST /send` y guarda de imagen por
  capacidad.
- `services/orchestrator`: `ATTENDED_CHANNELS` y guarda de canal/dirección como
  primera instrucción de `post_message`.

## Trazabilidad

- R1 → `contracts/tests/test_canal_abierto.py::test_channel_accepts_valid_slugs`
- R2 → `contracts/tests/test_canal_abierto.py::test_channel_rejects_invalid_slugs`
- R3 → `contracts/tests/test_canal_abierto.py::test_message_kind_has_exactly_six_values`
- R3 → `contracts/tests/test_canal_abierto.py::test_unknown_kind_video_is_rejected`
- R4 → `contracts/tests/test_canal_abierto.py::test_media_kind_requires_attachment`
- R5 → `contracts/tests/test_canal_abierto.py::test_attachment_type_must_match_kind`
- R6 → `contracts/tests/test_canal_abierto.py::test_non_media_kind_rejects_attachments`
- R7 → `contracts/tests/test_canal_abierto.py::test_media_kind_accepts_optional_caption`
- R8 → `contracts/tests/test_canal_abierto.py::test_attachments_are_limited_to_ten`
- R9 → `contracts/tests/test_canal_abierto.py::test_attachment_accepts_minimal_and_full_fields`
- R10 → `contracts/tests/test_canal_abierto.py::test_attachment_mime_type_rules`
- R11 → `contracts/tests/test_canal_abierto.py::test_attachment_name_rules`
- R12 → `contracts/tests/test_canal_abierto.py::test_attachment_size_rules`
- R13 → `contracts/tests/test_canal_abierto.py::test_https_url_rules`
- R14 → `contracts/tests/test_canal_abierto.py::test_attachment_rejects_binary_fields`
- R15 → `contracts/tests/test_canal_abierto.py::test_metadata_defaults_to_empty_object_and_accepts_json`
- R15 → `contracts/tests/test_canal_abierto.py::test_metadata_size_limit`
- R15 → `contracts/tests/test_canal_abierto.py::test_metadata_depth_limit`
- R16 → `contracts/tests/test_canal_abierto.py::test_metadata_size_limit`
- R17 → `contracts/tests/test_canal_abierto.py::test_metadata_depth_limit`
- R17 → `contracts/tests/test_canal_abierto.py::test_metadata_rejects_non_json_python_values`
- R17 → `contracts/tests/test_canal_abierto.py::test_metadata_rejects_deeply_nested_python_dict`
- R17 → `contracts/tests/test_canal_abierto.py::test_metadata_rejects_non_json_numbers`
- R18 → `contracts/tests/test_canal_abierto.py::test_metadata_must_be_object`
- R18 → `contracts/tests/test_canal_abierto.py::test_metadata_rejects_non_json_python_values`
- R19 → `contracts/tests/test_canal_abierto.py::test_direction_defaults_to_inbound_and_accepts_outbound`
- R20 → `contracts/tests/test_canal_abierto.py::test_outbound_rejects_button_and_unsupported`
- R21 → `contracts/tests/test_canal_abierto.py::test_capabilities_new_fields_have_defaults`
- R22 → `contracts/tests/test_canal_abierto.py::test_image_block_is_part_of_response_blocks`
- R23 → `contracts/tests/test_canal_abierto.py::test_image_block_rejects_missing_or_invalid_fields`
- R23 → `contracts/tests/test_canal_abierto.py::test_https_url_rules`
- R24 → `contracts/tests/test_canal_abierto.py::test_historical_payloads_validate_with_defaults`
- R25 → `contracts/tests/test_canal_abierto.py::test_serialization_omits_default_new_fields`
- R26 → `contracts/tests/test_canal_abierto.py::test_serialization_keeps_non_default_fields_and_round_trips`
- R27 → `contracts/tests/test_canal_abierto.py::test_new_names_are_exported_with_contract_values`
- R28 → `contracts/tests/test_canal_abierto_doc.py::test_normalized_message_table_lists_all_fields`
- R28 → `contracts/tests/test_canal_abierto_doc.py::test_attachment_table_lists_all_fields`
- R29 → `contracts/tests/test_canal_abierto_doc.py::test_response_blocks_table_lists_image_block`
- R29 → `contracts/tests/test_canal_abierto_doc.py::test_capabilities_table_lists_all_fields_with_defaults`
- R30 → `contracts/tests/test_canal_abierto_doc.py::test_generic_webhook_route_is_documented`
- R31 → `contracts/tests/test_canal_abierto_doc.py::test_generic_section_json_examples_validate`
- R32 → `contracts/tests/test_canal_abierto_doc.py::test_signature_rules_are_documented`
- R33 → `contracts/tests/test_canal_abierto_doc.py::test_signed_examples_are_verifiable`
- R34 → `contracts/tests/test_canal_abierto_doc.py::test_callback_is_documented`
- R35 → `contracts/tests/test_canal_abierto_doc.py::test_equivalence_table_maps_assignment_names`
- R36 → `contracts/tests/test_canal_abierto_doc.py::test_authentication_lists_generic_webhook`
- R37 → `contracts/tests/test_canal_abierto_doc.py::test_send_and_messages_document_temporary_rejections`
- R38 → `contracts/tests/test_canal_abierto_doc.py::test_assumption_s17_documents_limits_and_text_only`
- R39 → `services/telegram_gateway/tests/test_canal_abierto.py::test_send_unknown_channel_returns_422_without_sending`
- R39 → `services/telegram_gateway/tests/test_canal_abierto.py::test_send_unknown_channel_is_422_even_without_whatsapp`
- R40 → `services/telegram_gateway/tests/test_canal_abierto.py::test_send_image_block_is_rejected_on_current_channels`
- R40 → `services/telegram_gateway/tests/test_canal_abierto.py::test_send_response_allows_image_when_capability_is_declared`
- R40 → `services/telegram_gateway/tests/test_canal_abierto.py::test_send_response_rejects_image_without_capability`
- R41 → `services/telegram_gateway/tests/test_canal_abierto.py::test_current_adapters_keep_their_capabilities`
- R42 → `services/telegram_gateway/tests/test_canal_abierto.py::test_forwarded_payload_has_only_historical_keys`
- R43 → `services/orchestrator/tests/test_canal_abierto.py::test_post_messages_rejects_unattended_channel`
- R44 → `services/orchestrator/tests/test_canal_abierto.py::test_post_messages_rejects_outbound_direction`
- R45 → `services/orchestrator/tests/test_canal_abierto.py::test_media_kinds_get_unsupported_reply_without_persistence`
- R46 → `services/orchestrator/tests/test_canal_abierto.py::test_post_messages_accepts_media_kind`
- R47 → sin tests nuevos; suites existentes de `contracts/tests`, `contracts/examples`
  y `services/*/tests` se mantienen sin cambios (verificación de `./init.sh`).
- R48 → `contracts/tests/test_canal_abierto.py::test_attachment_requires_type_and_mime_type`

## Verificación

- Escritura: OpenCode (`opencode-go/deepseek-v4.1-flash`) en un solo intento,
  respuesta `done`; sin correcciones posteriores.
- `bash ./init.sh` (2026-11-21, Python 3.14.7 del `.venv`, pydantic 2.14.2):
  **3723 passed, 1 skipped**, 2 warnings ya existentes (deprecación de
  `httpx` en `starlette.testclient` y `model_fields` en instancia en
  `test_conversation_states.py:687`); «Todos los tests pasan».
- R47 / T16: `git status --porcelain -- contracts/tests contracts/examples services/*/tests`
  solo muestra los cuatro archivos nuevos (`??`), sin `M` ni `D`.
- `specs/contrato_canal_abierto/tasks.md`: T1–T17 marcadas `[x]`.
- `feature_list.json`: OpenCode no lo modificó (el diff es el del leader
  antes de esta sesión: #60 `in_progress` y aclaraciones de #62, #63, #65).
- Puntos del reviewer: R41 usa `ChannelCapabilities(**whatsapp_capabilities(...))`
  (`services/telegram_gateway/tests/test_canal_abierto.py`); los tres bloques
  de ejemplo de `CONTRATOS.md` usan tres comillas invertidas; `design.md`
  «Alcance» ya dice «R1–R27, R48».

## Notas para el reviewer

- `NormalizedMessage.attachments` usa `Field(max_length=...)` directamente en
  vez de `Annotated[list[Attachment], Field(max_length=...)]`. El
  comportamiento es el mismo (R8 en verde).

## Corrección pedida por el reviewer (ciclo 1 de 2)

Origen: `progress/review_code_contrato_canal_abierto.md` (CHANGES_REQUESTED).
Leer ese informe completo, sección «Cambios requeridos». Atender **solo** estos
dos hallazgos y no tocar nada más:

1. **R17 / R26 — `contracts/lazaro_contracts/channels.py` (línea ~48).** Quitar
   `JsonValue = Any` e importar `JsonValue` de `pydantic`, como fija
   `design.md` (`metadata: dict[str, JsonValue]`). Además, en el `json.dumps`
   de `_check_metadata`, pasar `allow_nan=False` para que `NaN`/`Infinity`
   den `ValidationError`. En `contracts/tests/test_canal_abierto.py`, añadir
   tests nuevos (docstring con `R17`/`R18`) que comprueben `ValidationError`
   al construir `NormalizedMessage` en Python con:
   - `metadata` con tuplas anidadas a profundidad mayor que 5
     (p. ej. `{"x": ((((((((1,),),),),),),),)}`);
   - un dict anidado con clave que no es texto (p. ej. `{"x": {1: "a"}}`);
   - un dict anidado de 100 000 niveles construido de forma iterativa (hoy da
     `RecursionError`; debe dar `ValidationError`);
   - `metadata` con `float("nan")` y con `float("inf")`.
   Deben seguir en verde: 4096 bytes válido y 4097 no, profundidad 5 válida y
   6 no, y el round trip de R26.
2. **R43 / R44 — `services/orchestrator/tests/test_canal_abierto.py`
   (líneas ~57-71).** En `test_post_messages_rejects_unattended_channel`
   (para cada canal parametrizado y el usuario `57300`) y en
   `test_post_messages_rejects_outbound_direction` (`whatsapp`/`57300`),
   registrar el consentimiento **antes** del POST con
   `env.repo.add_channel_privacy_consent(channel, user, env.settings.privacy_notice_version, notice_sha256(env.settings.privacy_notice_text), NOW)`
   para que `processed_messages == set()` pruebe de verdad que la guarda actúa
   antes de `mark_message_if_new`. Opcional: quitar de
   `_assert_nothing_happened` las comprobaciones repetidas (líneas 50 y 51).

No modificar tests ni ejemplos existentes de antes de #60 (R47), ni
`feature_list.json`, ni `specs/`.

## Resultado de la corrección (ciclo 1)

- `channels.py`: `JsonValue` se importa de `pydantic`; `_json_depth` tipa con
  `JsonValue`; `_check_metadata` usa `allow_nan=False`. `Any` ya no se importa.
- `contracts/tests/test_canal_abierto.py`: nuevos tests de R17/R18
  `test_metadata_rejects_non_json_python_values`,
  `test_metadata_rejects_deeply_nested_python_dict` y
  `test_metadata_rejects_non_json_numbers`; los tests previos de tamaño,
  profundidad y round trip (R15, R16, R17, R26) no cambian.
- `services/orchestrator/tests/test_canal_abierto.py`: helper `_consent` y
  consentimiento por canal/usuario `57300` antes del POST en R43 y R44; ambos
  tests ahora comprueban de verdad que no se llama a `mark_message_if_new`.
- No se aplicó la limpieza opcional de `_assert_nothing_happened`: siguen las
  comprobaciones repetidas de `processed_messages`. No afecta al resultado.
- Contexto: `scripts/run_opencode_writer.sh` solo admite
  `progress/review_<feature>.md` o `progress/impl_<feature>.md` como
  `--context`. Por eso los hallazgos de `review_code_contrato_canal_abierto.md`
  se copiaron arriba y se delegó con `--context progress/impl_contrato_canal_abierto.md`.
- Escritura: OpenCode `done` en un intento.
- `bash ./init.sh` (2026-11-21, tras la corrección): **3729 passed, 1 skipped**
  (+6 frente a 3723: 2 casos de `test_metadata_rejects_non_json_python_values`,
  1 de `test_metadata_rejects_deeply_nested_python_dict` y 3 de
  `test_metadata_rejects_non_json_numbers`), con los mismos 2 warnings que ya
  había; «Todos los tests pasan».
- R47: `git status --porcelain -- contracts/tests contracts/examples services/*/tests`
  sigue mostrando solo los cuatro archivos nuevos (`??`). `feature_list.json`
  y `specs/` no cambian en este ciclo.
- Trazabilidad actualizada: R17 y R18 incluyen los tests nuevos. R43 y R44
  conservan sus nombres de test, que ahora registran el consentimiento antes
  del POST.

