# Implementación #45 corregir_foreign_session_windows

## Resumen

Solo `services/orchestrator`. `PostgresRepository.foreign_session_windows` deja
de enviar `(%s IS NULL OR profile_id <> %s)` y usa dos sentencias separadas por
rama: sin `profile_id` filtra solo por `contact_id` con `(contact_id,)`; con
`profile_id` filtra por `contact_id = %s AND profile_id <> %s` con
`(contact_id, profile_id)`. Ninguna rama envía `None` como parámetro, así que
PostgreSQL no necesita inferir el tipo de un NULL (42P18). El mapeo a
`session_window` no cambia.

Archivos tocados:

- `services/orchestrator/orchestrator/adapters/repository.py`: únicamente
  `PostgresRepository.foreign_session_windows`.
- `services/orchestrator/tests/test_foreign_session_windows.py`: nuevo, con
  `Conn`/`Cursor` falsos que capturan `(sql, params)` y emulan 42P18.
- `specs/corregir_foreign_session_windows/tasks.md`: T1–T3 marcadas.

Sin cambios en `FakeRepository`, `domain.py`, firmas, contratos, esquema ni
configuración.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_foreign_session_windows.py::test_none_profile_filters_only_by_contact`
- R2 → `services/orchestrator/tests/test_foreign_session_windows.py::test_profile_filters_foreign_profiles`
- R3 → `services/orchestrator/tests/test_foreign_session_windows.py::test_none_profile_filters_only_by_contact`
- R3 → `services/orchestrator/tests/test_foreign_session_windows.py::test_profile_filters_foreign_profiles`
- R4 → `services/orchestrator/tests/test_foreign_session_windows.py::test_none_profile_maps_rows_in_order`
- R4 → `services/orchestrator/tests/test_foreign_session_windows.py::test_profile_maps_rows_in_order`
- R5 → `services/orchestrator/tests/test_panel_case_view.py::test_foreign_session_windows_are_hidden_with_and_without_profile` (existente, sin cambios)
- R5 → `services/orchestrator/tests/test_panel_pure.py::test_history_visible_excludes_foreign_session_windows` (existente, sin cambios)
- R6 → `services/orchestrator/tests/test_panel_case_view.py::test_case_without_profile_shows_no_client_and_no_memory` (existente, sin cambios)
- R6 → `services/orchestrator/tests/test_panel_case_view.py::test_foreign_session_windows_are_hidden_with_and_without_profile` (existente, sin cambios)

## Tasks

- T1–T3 completadas (código y tests nuevos).
- T4: revisadas por inspección; las pruebas de `FakeRepository` y del panel no
  tocan el SQL de Postgres y no se modificaron. Su ejecución verde queda cubierta
  por T5.
- T5 (`./init.sh` verde) queda para Claude, que ejecuta la verificación al
  cerrar la sesión.

## Verificación (Claude, implementer puente)

- Diff revisado: solo `PostgresRepository.foreign_session_windows` cambia en
  `repository.py` (dos ramas SQL, sin `IS NULL` ni parámetros `None`; mapeo
  `session_window` intacto). Test nuevo conforme a T2/T3.
- T4: `test_panel_case_view.py` y `test_panel_pure.py` sin modificaciones
  (`git status` limpio para ambos); las pruebas listadas en la trazabilidad
  existen y pasan dentro de la suite completa.
- T5: `C:\Program Files\Git\bin\bash.exe ./init.sh` ejecutado una vez →
  exit 0, `3052 passed, 1 skipped, 2 warnings in 113.70s` (Python 3.14.7,
  `.venv`), "Todos los tests pasan", modo supervisado. Sin intentos de
  corrección necesarios.
- T1–T5 marcadas en `specs/corregir_foreign_session_windows/tasks.md`.
- Trazabilidad R1–R6 → test confirmada (sección anterior).
- Pendiente: review de código por el reviewer. No se tocó `feature_list.json`
  ni se marcó `done`.
