# Revisión de spec — feature #60 `contrato_canal_abierto`

**Veredicto:** APPROVED (segunda y última revisión, solo de los puntos pedidos)

## Puntos corregidos

1. **R15:** ahora tiene un solo `DEBE` («… con `{}` cuando el campo falta»).
   Sigue cubierto por T8 (`test_metadata_defaults_to_empty_object_and_accepts_json`,
   `test_metadata_size_limit`, `test_metadata_depth_limit`).
2. **R31:** pasa a ser un requisito sobre `CONTRATOS.md`, con un solo `DEBE`.
   T11 `test_generic_section_json_examples_validate` comprueba que están los
   ejemplos de entrada (con adjunto y `metadata`) y de callback `outbound`, y que
   todos los bloques validan.
3. **R9 / R48:** R9 ya no lleva la frase suelta. R48 nuevo («SI un adjunto llega
   sin `type` o sin `mime_type` ENTONCES … `ValidationError`») está en T3 y en T8
   (`test_attachment_requires_type_and_mime_type`). También figura en la tabla de
   cobertura (criterio 2) y en el reparto por servicio («R1–R38 y R48»).
4. **R41 / T13:** el test envuelve el `dict` en
   `ChannelCapabilities(**whatsapp_capabilities(...))`.
5. **Recuento de `DEBE`:** comprobado automáticamente. Cada uno de los 48
   requisitos tiene exactamente un `DEBE`/`DEBEN`.
6. **`design.md`:**
   - La nota de `exclude_if` dice ahora «≥ 2.12» y cita el wheel 2.12.0.
   - Aclara que en `CONTRATOS.md` los bloques usan tres comillas invertidas
     (línea 416).
   - La justificación de los 10 adjuntos se apoya solo en Telegram.
   - Las dos firmas de ejemplo siguen coincidiendo con `secreto-de-ejemplo`
     (las recalculé otra vez).
7. **`ATTENDED_CHANNELS`:**
   - El design (comentario y párrafo de la sección `orchestrator`) y el
     acceptance de #65 en `feature_list.json` asignan la retirada a #65.
   - El acceptance de #63 aclara que, hasta #65, el orquestador responde 422 a
     un canal nuevo.
   - El orden de dependencias es coherente: #65 depende de #61, #63 y #64.
8. **T17:** la trazabilidad cubre R1–R48.

## Notas no bloqueantes

1. El acceptance de #62 no menciona que el orquestador responde 422 hasta #65.
   Su `spec_author` debe tenerlo en cuenta al diseñar la entrega y sus pruebas.
2. `design.md` («Alcance», línea 13) sigue diciendo «R1–R27» para los modelos
   del contrato. R48 también pertenece al contrato y ya está en T3 y T8.
