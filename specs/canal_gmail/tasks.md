# Tareas — Canal Gmail

- [x] T1 — Añadir cliente HTTP OAuth/Gmail API inyectable y fake. Cubre: R1, R3, R4, R8-R10.
- [x] T2 — Registrar `GmailChannelFactory`, validar dirección/config, exponer el campo en el panel y normalizar correo entrante sin descargar adjuntos. Cubre: R1-R2, R4, R7, R10, R12.
- [x] T3 — Añadir repositorio fake/Postgres del cursor Gmail con creación de esquema segura. Cubre: R3, R5-R6, R13.
- [x] T4 — Implementar `GmailSyncService` incremental, exclusión de correo propio, entrega idempotente al orquestador, reintento y error de cursor vencido. Cubre: R3-R7, R13-R15.
- [x] T5 — Implementar respuesta MIME de texto al hilo Gmail y manejo de errores sin contenido sensible en logs. Cubre: R8-R10, R15.
- [x] T6 — Inyectar dependencias y exponer rutas protegidas de sincronización y reinicio de cursor; verificar canal activo. Cubre: R11-R12.
- [x] T7 — Añadir `scripts/sincronizar_gmail.py` y tests de selección de canales, token y códigos de salida. Cubre: R16-R17.
- [x] T8 — Documentar alta OAuth, scopes, creación de canal, scheduler, reinicio del cursor y privacidad. Añadir comprobación documental de contrato/README. Cubre: R18.
- [x] T9 — Ejecutar `./init.sh`, revisar trazabilidad requirement→test y registrar evidencia en `progress/impl_canal_gmail.md`. Cubre: R1-R18.
