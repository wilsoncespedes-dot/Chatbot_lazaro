# Spec review — #67 etiqueta_origen_canal

**Veredicto:** SPEC_APPROVED

- Cobertura: los 9 criterios de `acceptance` están cubiertos por R1-R21.
- EARS y verificabilidad: cada R tiene un patrón EARS y se puede comprobar con un test concreto.
- Diseño: respeta las 3 capas y no añade dependencias. Reutiliza `ChannelDirectory`, `contrast_ratio` e `icon_glyph` de #65/#66, que existen en el repo. Incluye alternativas descartadas y supuestos.
- Tasks: T1-T9 están en `[ ]`, en orden, y cubren R1-R21.
- Nada peligroso.

Observaciones no bloqueantes (el implementador puede resolverlas):
- R3 mezcla «NO DEBE» y «DEBE». Se puede leer como un único requisito.
- `contrast_ratio` e `icon_glyph` viven en `admin_channels.py`. `channel_label.py` debe importarlos sin crear una dependencia circular con `admin`.
