# Implementación — #74 `servidor_mcp_lectura`

## Resumen

- Nuevo servicio `services/mcp_lectura/` con SDK oficial `mcp` (declarado en
  `requirements.txt`; se importa de forma perezosa para que el resto del
  monorepo no dependa del SDK al arrancar). Expone solo `buscar_manuales` y
  `ofertas_demo` con `readOnlyHint=True`, exige `X-Service-Token` salvo
  `/health`, no publica puertos en compose y audita cada llamada.
- `ofertas_demo` usa `SELECT` parametrizado en transacción `READ ONLY`; la tabla
  `demo_ofertas` tiene `CHECK (es_demo)` y las filas salen con
  `es_demo=true`/`etiqueta="DEMOSTRACIÓN"`.
- Orquestador como cliente MCP: `TOOL_MATRIX` incluye
  `consultar_herramientas_mcp` solo en `active`; el `cliente_id` sale de la
  sesión y viaja en `X-Cliente-Id`, fuera del esquema de la herramienta; se
  filtran argumentos no declarados, se aplica la lista blanca de herramientas,
  el límite de pasos, el fallback a RAG y el aviso de demostración.
- Panel `GET /admin/mcp` (solo admin) lista las ofertas con la etiqueta
  «DEMOSTRACIÓN» y muestra «no disponible» con `200` si el MCP falla.
- Configuración `MCP_*` en `.env.example`, servicio `mcp_lectura` sin `ports`,
  `ollama` bajo el perfil `ollama` y documentación en `docs/mcp.md`.

## Nota de entorno

`mcp>=1.2,<2` está declarado en `services/mcp_lectura/requirements.txt` y
`services/orchestrator/requirements.txt` (design §2). En este entorno el
`.venv` aún no tiene el paquete instalado; los tests del servidor validan el
registro de herramientas, adaptadores y middleware con un app MCP inyectado. El
binding real `FastMCP` / `streamablehttp_client` requiere la instalación previa
indicada como prerrequisito humano en `tasks.md`; `./init.sh` lo ejecuta Claude
como parte de la verificación.

## Trazabilidad

- R1 → `services/mcp_lectura/tests/test_tools.py::test_lists_only_two_tools`, `test_server_registration.py::test_build_mcp_registers_exactly_two_read_only_tools`
- R2 → `services/mcp_lectura/tests/test_tools.py::test_all_tools_read_only_hint`, `test_server_registration.py::test_build_mcp_registers_exactly_two_read_only_tools`
- R3 → `services/mcp_lectura/tests/test_tools.py::test_demo_query_is_select_read_only`
- R4 → `services/mcp_lectura/tests/test_tools.py::test_buscar_manuales_only_calls_search`
- R5 → `services/mcp_lectura/tests/test_tools.py::test_no_identity_field_in_schemas`, `test_server_registration.py::test_build_mcp_registers_exactly_two_read_only_tools`
- R6 → `services/mcp_lectura/tests/test_security.py::test_missing_token_401`, `::test_wrong_token_401`
- R7 → `services/mcp_lectura/tests/test_security.py::test_health_without_token`
- R8 → `services/mcp_lectura/tests/test_security.py::test_compose_publishes_no_port`
- R9 → `services/mcp_lectura/tests/test_audit.py::test_audit_row_fields`, `::test_tool_error_is_audited_and_reraised`
- R10 → `services/mcp_lectura/tests/test_audit.py::test_audit_has_no_argument_values`
- R11 → `services/mcp_lectura/tests/test_audit.py::test_audit_failure_returns_error_without_data`, `::test_audit_failure_on_tool_error_fails_closed`
- R12 → `services/mcp_lectura/tests/test_tools.py::test_demo_rows_marked`
- R13 → `services/mcp_lectura/tests/test_tools.py::test_demo_ddl_enforces_marker`
- R14 → `services/orchestrator/tests/test_mcp_matrix.py::test_mcp_tool_only_in_active`
- R15 → `services/orchestrator/tests/test_mcp_matrix.py::test_router_prompt_hides_mcp_when_disabled`, `::test_disabled_never_contacts_mcp`
- R16 → `services/orchestrator/tests/test_mcp_matrix.py::test_denied_in_with_advisor_no_mcp_call`
- R17 → `services/orchestrator/tests/test_mcp_flow.py::test_cliente_id_comes_from_session`
- R18 → `services/orchestrator/tests/test_mcp_flow.py::test_model_cliente_id_arg_is_dropped`
- R19 → `services/orchestrator/tests/test_mcp_flow.py::test_unlisted_tool_rejected`
- R20 → `services/orchestrator/tests/test_mcp_flow.py::test_max_tool_steps`
- R21 → `services/orchestrator/tests/test_mcp_flow.py::test_mcp_down_falls_back_to_rag_and_logs`
- R22 → `services/orchestrator/tests/test_mcp_flow.py::test_no_tool_call_falls_back_to_rag`
- R23 → `services/orchestrator/tests/test_mcp_flow.py::test_demo_notice_appended`
- R24 → `services/orchestrator/tests/test_mcp_flow.py::test_tool_calls_audit_detail`
- R25 → `services/orchestrator/tests/test_mcp_llm.py::test_tools_sent_to_configured_endpoint`
- R26 → `services/orchestrator/tests/test_mcp_channels.py::test_same_answer_telegram_and_simulado`
- R27 → `services/orchestrator/tests/test_mcp_admin.py::test_admin_lists_demo_offers_with_badge`
- R28 → `services/orchestrator/tests/test_mcp_admin.py::test_admin_mcp_down_shows_unavailable`
- R29 → `services/orchestrator/tests/test_mcp_admin.py::test_admin_mcp_requires_session`
- R30 → `services/mcp_lectura/tests/test_config_files.py::test_env_example_declares_mcp_vars`, `services/orchestrator/tests/test_mcp_matrix.py::test_mcp_settings_defaults`
- R31 → `services/mcp_lectura/tests/test_config_files.py::test_ollama_under_profile`
- R32 → `services/mcp_lectura/tests/test_config_files.py::test_docs_mcp_covers_ollama_and_remote`

## Archivos existentes ajustados

- `services/orchestrator/tests/test_harness_matrix.py`: la matriz pasa de seis a
  siete herramientas por el nuevo `consultar_herramientas_mcp` (R14).
- `docs/architecture.md` y `contracts/CONTRATOS.md`: nota breve del servicio MCP;
  no hay modelos HTTP nuevos (el protocolo es MCP).

## Fallos de init.sh (intento 1)

3 tests rotos que debe corregir el writer (sin tocar feature_list.json):
1. `services/orchestrator/tests/test_config.py::test_only_health_and_messages_routes_exposed`: el conjunto de rutas esperado no incluye `/admin/mcp` (añadirla al esperado, es ruta legítima del design).
2. `services/orchestrator/tests/test_mcp_llm.py::test_tools_sent_to_configured_endpoint`: RuntimeError `raise_for_status` sin request en la respuesta httpx (construir `httpx.Response(..., request=httpx.Request(...))` en el fake o ajustar el adaptador).
3. `services/orchestrator/tests/test_orchestrator_app.py::test_requirements_txt_matches_design`: requirements.txt del orquestador tiene `mcp` (y quizá `websockets`) que el test/design no listan; alinear el test con design §2 (mcp declarado) y verificar lista exacta.

## Correcciones aplicadas (intento 2)

Solo tests; no se tocó código de aplicación ni `feature_list.json`.

1. `test_config.py`: `/admin/mcp` añadida al conjunto esperado de rutas
   (ruta legítima del design, R27).
2. `test_mcp_llm.py`: la respuesta falsa de `httpx` incluye `request=httpx.Request(...)`
   para que `raise_for_status()` funcione (R25).
3. `test_orchestrator_app.py`: `mcp` añadida a la lista ordenada de dependencias
   esperadas, conforme a design §2.

## Resultado de init.sh (tras corrección)

4667 passed, 1 skipped; "Entorno listo". Trazabilidad R<n> → test presente arriba.
