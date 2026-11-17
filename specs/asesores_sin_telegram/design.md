# Design — asesores_sin_telegram (#65)

- `advisor_panel.render_advisor_home` pierde el parámetro `linked` y su aviso;
  `advisor_routes.home` deja de pasarlo.
- `advisor_routes`: se elimina `TelegramNotLinked` y los 8 `try/except` que
  la capturaban (ya nada la lanzaba: la identidad del asesor es su
  `profile_id`). Se elimina `telegram_not_linked` de `ERROR_MESSAGES`.
- `admin.render_profiles` sin columnas de Telegram ni botón; se borran
  `admin.render_link` y la ruta `POST /admin/profiles/{id}/link-token`.
- Fuera de alcance (se conserva): API interna `POST /profiles/{id}/link-token`
  con token de servicio y el `/start <token>` de Telegram (feature #20), que
  también usan otros perfiles; el comando `/db_query` por Telegram exige un
  asesor vinculado y deja de estar disponible para asesores nuevos.
