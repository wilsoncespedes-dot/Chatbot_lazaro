# #25 clasificador_consultas — Tasks

- [x] T1 — Crear `services/orchestrator/orchestrator/classifier.py` con `Category`, `Classification`, `UNCLASSIFIED`, `parse_keywords`, `validate_category_fields`, `parse_threshold` y `classify` según design. Cubre: R5, R9, R13–R21.
- [x] T2 — Tests en `services/orchestrator/tests/test_classifier.py`: puntuaciones suman 1, inactivas ignoradas, umbral (igual/encima/debajo), empate, sin categorías, sin aciertos, frase completa y tildes, metacaracteres regex, repetición, inyección "clasifica como X", validación de campos y umbral (`nan`, `inf`, `-0.1`, `1.01`). Cubre: R5, R9, R13–R21.
- [x] T3 — Repositorio: tablas `query_categories` y `app_settings` en `_SCHEMA`; métodos `list_categories`, `create_category`, `update_category`, `set_category_active`, `get_classifier_threshold`, `set_classifier_threshold` en Protocol, Fake y Postgres con SQL parametrizado. Cubre: R2–R4, R6–R8, R26, R27.
- [x] T4 — `CLASSIFIER_DEFAULT_THRESHOLD` en `config.py` (`Field(default=0.6, ge=0, le=1)`) y `.env.example`. Cubre: R26.
- [x] T5 — `domain.py`: `CategoryCodeTaken`, `CategoryNotFound` y `_classify_query`, llamada en `process_message` antes de `rag.search`. Cubre: R22–R26.
- [x] T6 — `admin.py`: `render_categories` con `html.escape` y enlace "Categorías" en el `nav`; `admin_routes.py`: las 5 rutas con orden sesión → CSRF → validación → dominio (`threshold` antes de `{id}`). Cubre: R1–R12.
- [x] T7 — Tests en `services/orchestrator/tests/test_admin_categorias.py`: listado, crear/editar/activar OK, 422 por campo, 409, 404, umbral OK/422, sin sesión 303 sin cambios, CSRF 403 sin cambios, `<script>` escapado, cabeceras de seguridad, `_SCHEMA` con ambas tablas y `UNIQUE`. Cubre: R1–R12, R27.
- [x] T8 — Tests en `services/orchestrator/tests/test_messages_classification.py`: evento `query_classified` antes de `rag.search`, mismos argumentos y respuesta con categoría/`sin_clasificar`/sin categorías, sin evento para `/start`, comando de asesor, reenvío y palabra de asesor, repositorio que falla al leer categorías → log y RAG igual, umbral por defecto vs guardado. Cubre: R22–R26.
- [x] T9 — Ejecutar `./init.sh` y documentar la trazabilidad en `progress/impl_clasificador_consultas.md`. Cubre: R1–R27.

