# Review — feature #74 servidor_mcp_lectura

**Veredicto:** APPROVED

## Trazabilidad requirements <-> tests
- R1-R32: [x] todos mapeados en `progress/impl_servidor_mcp_lectura.md`; verificado que existen los tests clave
  (`test_lists_only_two_tools`, `test_demo_ddl_enforces_marker`, `test_same_answer_telegram_and_simulado`,
  `test_admin_mcp_requires_session`, `test_tools_sent_to_configured_endpoint`, etc.).

## Tasks completas
- T1-T23: [x] todas en `[x]` en `specs/servidor_mcp_lectura/tasks.md`.

## Dependencia `mcp` no instalada
Aceptable: `mcp>=1.2,<2` (MIT) está declarada y acotada en ambos `requirements.txt` y en design §2; los imports
del SDK son perezosos (`server.py:63-65`, `adapters/mcp.py:124,161`); los tests usan app/cliente inyectado y fakes
(el design y R-trazabilidad exigen pruebas con `FakeMcpClient`). Riesgo residual: el binding real FastMCP/streamable-http
no está ejercitado hasta instalar el paquete; verificar con un smoke manual antes de activar `MCP_ENABLED=true`
(por defecto `false`).

## Verificación
- `./init.sh`: 4667 passed, 1 skipped, "Entorno listo".
- `mcp_lectura` sin `ports` (solo `expose`), SELECT parametrizado con `SET TRANSACTION READ ONLY`.

## Checkpoints
- C1: [x]  C2: [x]  C3: [x]  C4: [x]  C5: [x]  C6: [x]

## Cambios requeridos
Ninguno bloqueante.
