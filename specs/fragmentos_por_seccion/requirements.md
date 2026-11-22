# Requirements — fragmentos_por_seccion (#63)

Servicio: `rag` (`domain.chunk_text`, `extraction.extract_text`). Problema:
el troceo juntaba todo el texto en una línea y cortaba cada 1000 caracteres
exactos, partiendo palabras, pasos y secciones; los fragmentos no decían de
qué sección eran y las celdas de las tablas DOCX quedaban sueltas.

## R1
El sistema DEBE trocear cada sección del documento por separado, sin que un
fragmento mezcle texto de dos secciones.

## R2
Cada fragmento DEBE empezar con la ruta de sus dos últimos niveles de título
("Facturas > Anulación: …"); son títulos las líneas Markdown (`#`…`######`) y
las numeradas de varios niveles ("2.1 Anulación"), no los pasos ("1. Ingresa").

## R3
Los fragmentos NO DEBEN superar `chunk_size` caracteres y DEBEN cortarse entre
frases; una frase más larga se parte por palabras y solo una palabra más larga
que el fragmento se parte por caracteres.

## R4
Cada fragmento DEBE empezar con las frases finales del anterior de la misma
sección que quepan en `chunk_overlap` caracteres.

## R5
CUANDO se extrae un DOCX, los párrafos con estilo de título ("Heading N",
"Título N") DEBEN salir como líneas Markdown de nivel N.

## R6
CUANDO se extrae un DOCX, las celdas de cada fila de una tabla DEBEN salir en
una misma línea separadas por " | ", y cada fila DEBE tratarse como una frase.
