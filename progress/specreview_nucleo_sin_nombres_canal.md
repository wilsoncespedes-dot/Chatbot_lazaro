# Spec review — #65 nucleo_sin_nombres_canal (segunda vuelta)

**Veredicto:** APPROVED

El bloqueo de la primera vuelta está resuelto con la opción (a).
- `FakeChannelDirectory` ya no contiene nombres de canal. `default_infos` está vacío en producción (design.md §3).
- Los `ChannelInfo` de prueba viven en `tests/fakes.py` y los puebla un fixture `autouse`.
- T8 y la sección «Archivos» de §2 están actualizadas.
- Ya no hay contradicción con R36 ni R37. `adapters/channels.py` no importa `LEGACY_CHANNEL`.

Comprobado:
- Los siete criterios de acceptance están cubiertos por R1 a R43.
- Los R siguen EARS con un solo DEBE.
- Las tasks T1 a T22 están en `[ ]`, en orden, y cubren todos los R.
- El diseño respeta `docs/architecture.md`: el orquestador consulta al gateway por HTTP, sin leer su base.
- No hay dependencias nuevas.
- Hay alternativas descartadas y supuestos (S1 a S6).
- No hay nada peligroso. La migración es aditiva e idempotente, sin borrado de datos.
