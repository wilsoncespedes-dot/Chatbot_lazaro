# Tasks — #66 `panel_administracion_canales`

- [x] T1 — Contrato: `credential_hint`, `ChannelInfo.credential_hints`, `CHANNEL_ICONS`; exportar; documentar en `CONTRATOS.md`; test `contracts/tests/test_panel_canales_contrato.py`. Cubre: R1, R2, R6.
- [x] T2 — Gateway: columna `pistas_credenciales`, `ChannelRecord`/`ChannelChanges.credential_hints`, cálculo en create/update, `_info`; `simulado` acepta `consent_mode`; test `test_canales_pistas.py` (pistas, vacío, simulado, inactivo 404 y `/send` rechazado). Cubre: R3, R4, R5, R27.
- [x] T3 — Orquestador: `adapters/channel_admin.py` (Http + Fake + errores), `Adapters.channel_admin`, `ChannelDirectory.invalidate()`, `GATEWAY_PUBLIC_BASE_URL`. Cubre: R18, R19, R29.
- [x] T4 — `admin_channels.py` puro: color/contraste, credenciales, formulario, URL de webhook. Cubre: R15, R16, R17, R20.
- [x] T5 — Vista `render_channels` + `canales.js` + enlace en la navegación. Cubre: R9, R10, R11, R14, R20, R21, R30, R31.
- [x] T6 — Rutas `/admin/canales…` con sesión admin, CSRF, auditoría y errores. Cubre: R7, R8, R12, R13, R22–R26, R32.
- [x] T7 — Tests `test_admin_canales.py` (permisos, CSRF, validaciones, alta con secreto, edición, entorno, copiar URL, ver/regenerar con auditoría, pistas, activar/desactivar, errores del gateway, bandeja con canal inactivo, invalidación). Cubre: R7–R32.
- [x] T8 — `./init.sh` verde e informe `progress/impl_panel_administracion_canales.md`. Cubre: todas.
