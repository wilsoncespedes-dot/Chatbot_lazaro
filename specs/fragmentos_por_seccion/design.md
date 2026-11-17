# Design — fragmentos_por_seccion (#63)

- `_sections(text)`: recorre las líneas; `_heading()` reconoce Markdown y
  numerados con punto interior (y sin puntuación final). Pila de títulos por
  nivel; la ruta usa los dos últimos. El cuerpo de cada sección se normaliza
  (espacios colapsados, como antes).
- `_units()`: frases (`(?<=[.!?…])\s+`); frase > presupuesto → palabras;
  palabra > presupuesto → `_window` (la ventana antigua).
- `_pack()`: agrupa unidades hasta `size - len(prefijo)`; si el prefijo deja
  menos de max(20, size/4) se omite; solapamiento con las unidades finales
  que quepan en `overlap`.
- `extraction._docx_paragraph` / `_docx_row`.
- Sin cambios de contrato ni de esquema; afecta solo a manuales nuevos o
  vueltos a subir.
