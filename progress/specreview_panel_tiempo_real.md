# Spec review — #53 panel_tiempo_real

**Veredicto:** SPEC_APPROVED

- Cobertura: los 6 criterios de `acceptance` quedan cubiertos (tabla de trazabilidad de requirements.md). Los R1–R35 están en EARS, cada uno con un solo `DEBE`. Todos se pueden verificar y todos tienen tasks y tests nombrados (T12–T18).
- Origin y sesión: el handshake se rechaza antes de `accept()`. R3–R5 exigen `Origin` presente y coincidencia exacta. Con la lista vacía se compara con `Host` (S1). La cookie es `SameSite=strict`. El token no viaja en la URL, así que no hay fuga por el log de uvicorn. R6 revalida la sesión en cada ciclo. R8 evita renovar la presencia. R9 pone un límite por perfil.
- Aislamiento por caso: R11 filtra con `handover.list_cases`, y R12 falla cerrado. R13 limita los eventos a `type`, `id` y `case_id`. El contenido solo sale por fragmentos HTTP con la autorización normal (R24, R25), y el CSRF no viaja por el websocket.
- CSP: R29 define directivas estrictas sin `unsafe-*`. R28 prohíbe `eval`, scripts inline y CDN, y el JS se sirve del mismo origen. El CSP del panel de administración no cambia.
- Fallback: R32, R33 y R35 cubren el reintento con backoff, el sondeo, `<noscript>` con refresh y el interruptor. R34 mantiene las acciones como formularios POST con CSRF.
- Multi-instancia: R15 y R19 usan la tabla `panel_events` de Postgres, con el evento insertado en la misma transacción que el mensaje, así que sirve aunque otro proceso guarde el mensaje. R20 evita duplicados con la ventana de solape. R21 y R22 cubren la retención y la supresión. Las alternativas descartadas (Redis, LISTEN/NOTIFY, eventos en memoria) están documentadas.
- Dependencias: `websockets>=13,<16` (BSD-3-Clause) se declara en design.md con versión y licencia. El humano la instala antes de implementar y los tests no la necesitan. No hay otras dependencias nuevas y no se usa Redis.
- Tasks: las 20 están en `[ ]`, en orden y con sus R. Entre todas cubren R1–R35.

Notas no bloqueantes para el implementer:
- El límite de R9 es por instancia, como dice el propio requisito.
- El conjunto `seen` de cada conexión debe podarse con la ventana de solape para que no crezca sin límite.
- Antes de ejecutar real, verificar que el proxy preserve `Host` o fijar `PANEL_WS_ALLOWED_ORIGINS` (S1).
