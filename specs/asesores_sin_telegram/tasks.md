# Tasks — asesores_sin_telegram (#65)

- [x] T1 Inicio de asesores sin aviso ni parámetro `linked` (R1).
- [x] T2 Quitar `TelegramNotLinked` y `telegram_not_linked` (R2).
- [x] T3 Perfiles sin columnas de Telegram ni botón; borrar ruta y `render_link` (R3, R4).
- [x] T4 Pruebas en `tests/test_asesores_sin_telegram.py`, ajustes en `test_admin.py`, `test_rediseno_identidad.py`, `test_config.py`; `./init.sh`.
- [x] T5 Revisión estática final aprobó el ajuste para permitir que asesores sin Telegram tomen conversaciones.
- [x] T6 Intentar la suite tras el ajuste final: `./init.sh` falló antes de pytest por CRLF en `find_python.sh`, y el Python de Windows no tiene pytest. Estado cerrado por instrucción del usuario tras revisión estática aprobada.
