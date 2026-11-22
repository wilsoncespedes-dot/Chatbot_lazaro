# Spec review — #71 respuestas_rapidas_bot

**Veredicto:** SPEC_APPROVED

- Cobertura: los 5 criterios de `acceptance` están cubiertos por R1-R36 (tabla y administración, orden y estados, imagen y degradación, sin contenido sembrado, pruebas).
- EARS y verificabilidad: los R<n> usan patrones válidos con un solo DEBE, y el mapa de pruebas de `requirements.md` los hace comprobables.
- Diseño: respeta las 3 capas y no añade dependencias. Incluye alternativa descartada y la sección de supuestos con defaults configurables. El nombre de tabla `quick_replies` (inglés) difiere del `respuestas_rapidas` del acceptance, lo que no bloquea. La ruta de media pública y sin autenticación está acotada por id aleatorio, firma binaria y nosniff.
- Tasks: T1-T16 están en `[ ]`, ordenadas, con R<n>, y entre todas cubren R1-R36.
- Seguridad: el spec no borra datos del usuario ni usa la red externa, y no toca archivos fuera del repo.

Observación no bloqueante: en T10, verificar que el evento `quick_reply` sea un tipo de evento admitido por el registro de eventos existente.
