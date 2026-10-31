# Requirements — evaluacion

Feature #8. Herramienta de evaluación en `eval/` (no es un servicio). Todos los R se verifican con tests en `eval/tests/` salvo que se indique otra cosa. Ninguna prueba usa red real: el cliente HTTP se sustituye por una versión falsa.

## Preguntas y manual de ejemplo

## R1
El sistema DEBE incluir `eval/preguntas.json` con una lista de al menos 15 preguntas, cada una con `id` único, `pregunta`, `tipo` (`responde` o `no_responde`) y, para `responde`, `fragmento_esperado` (texto literal contenido en el manual de ejemplo) y opcionalmente `chunk_id_esperado`.

## R2
El sistema DEBE incluir en `eval/preguntas.json` al menos 10 preguntas de tipo `responde`.

## R3
El sistema DEBE incluir en `eval/preguntas.json` al menos 5 preguntas de tipo `no_responde`.

## R4
El sistema DEBE incluir en `eval/manual_ejemplo/` un manual pequeño en texto (`.md` o `.txt`) con contenido inventado, sin datos personales ni de clientes reales.

## R5
El sistema DEBE garantizar que el `fragmento_esperado` de cada pregunta `responde` aparece literalmente (ignorando mayúsculas y espacios repetidos) en el texto de `eval/manual_ejemplo/`.

## R6
SI una pregunta del archivo carga con campos obligatorios ausentes, `id` repetido o `tipo` desconocido ENTONCES el cargador de preguntas DEBE lanzar `ValueError` indicando el `id` o la posición afectada.

## Puntuación (lógica pura, sin red)

## R7
El módulo `eval/scoring.py` NO DEBE importar librerías de red (`httpx`, `requests`, `urllib`, `socket`) ni leer variables de entorno.

## R8
CUANDO, en modo `rag`, una pregunta `responde` obtiene resultados en los que algún texto contiene el `fragmento_esperado` (comparación normalizada) o algún `chunk_id` coincide con `chunk_id_esperado`, el sistema DEBE puntuarla como `acierto_recuperacion`.

## R9
CUANDO, en modo `rag`, una pregunta `responde` obtiene una lista vacía o resultados sin el fragmento esperado, el sistema DEBE puntuarla como `fallo_recuperacion` y registrarla en la lista de fallos con su `id` y el motivo.

## R10
CUANDO una pregunta `no_responde` obtiene una lista vacía de resultados (modo `rag`) o el texto de rechazo configurado (modo `orquestador`), el sistema DEBE puntuarla como `rechazo_correcto`.

## R11
CUANDO una pregunta `no_responde` obtiene resultados no vacíos (modo `rag`) o un texto distinto del rechazo configurado (modo `orquestador`), el sistema DEBE puntuarla como `respuesta_inventada` y registrarla en la lista de fallos.

## R12
CUANDO una pregunta `responde` recibe el texto de rechazo en modo `orquestador`, el sistema DEBE puntuarla como `rechazo_indebido` y registrarla en la lista de fallos.

## R13
CUANDO se agregan los resultados individuales, el sistema DEBE calcular el resumen con: total de preguntas, aciertos de recuperación sobre preguntas `responde`, rechazos correctos sobre preguntas `no_responde`, número de respuestas inventadas y la lista de fallos.

## R14
SI el conjunto de resultados no contiene preguntas de un tipo ENTONCES el cálculo de proporciones DEBE devolver `None` para ese tipo, sin lanzar división por cero.

## R15
CUANDO se genera el informe, el sistema DEBE producir Markdown con los cuatro bloques del resumen de R13 y una sección «Fallos» que lista cada fallo (o «Ninguno» si no hay).

## Ejecución (capa de red)

## R16
CUANDO se ejecuta `python eval/run_eval.py --url <url> --modo rag`, el sistema DEBE llamar a `POST <url>/search` con `query` igual a la pregunta y `top_k` igual a `--top-k` (por defecto el valor de `RAG_TOP_K`, o 5 si no está definida).

## R17
CUANDO se ejecuta con `--modo orquestador`, el sistema DEBE enviar cada pregunta con `POST <url>/messages` según `lazaro_contracts.MessageRequest`, con un `chat_id` único por pregunta.

## R18
SI el orquestador no entrega ninguna respuesta al receptor dentro de `--espera` segundos ENTONCES el sistema DEBE puntuar la pregunta como `sin_respuesta` y registrarla en la lista de fallos.

## R19
SI una llamada HTTP falla (error de conexión, `401`, `5xx`) ENTONCES el sistema DEBE puntuar esa pregunta como `error`, con el código o la causa en `detail`, y registrarla en la lista de fallos.

## R20
CUANDO termina la ejecución, el sistema DEBE escribir `eval/resultados_<AAAA-MM-DD>.md` con el informe de R15 y la URL y el modo usados.

## R21
CUANDO se ejecuta con `--preguntas <ruta>` (repetible), el sistema DEBE cargar esas preguntas en lugar de `eval/preguntas.json`, para añadir las preguntas de un manual real sin tocar el archivo de ejemplo.

## R22
DONDE se pasa `--umbral-minimo-aciertos <x>` (0 a 1), el sistema DEBE terminar con código distinto de 0 si la proporción de aciertos de recuperación es menor que `x`.

## R23
SI falta `SERVICE_TOKEN` en el entorno ENTONCES el sistema DEBE terminar con código distinto de 0 y un mensaje claro, sin enviar ninguna petición.

## R24
El sistema NO DEBE incluir el valor de `SERVICE_TOKEN` en el informe ni en la salida estándar.

## Requisitos añadidos tras la revisión

## R25
CUANDO el sistema llama a `POST <url>/search` o a `POST <url>/messages`, DEBE enviar el encabezado `X-Service-Token` con el valor de `SERVICE_TOKEN`.

## R26
CUANDO se ejecuta con `--modo orquestador`, el sistema DEBE tomar como respuesta del bot el texto capturado por un receptor local que hace de gateway (`POST /send`) para el `chat_id` de la pregunta, esperando como máximo `--espera` segundos por pregunta (por defecto 30).

## R27
CUANDO termina la ejecución y alguna pregunta fue puntuada como `error`, el sistema DEBE terminar con código de salida distinto de 0.

## R28
CUANDO una pregunta se puntúa como `sin_respuesta` o `error`, el sistema DEBE continuar con la pregunta siguiente.

## R29
CUANDO, en modo `orquestador`, una pregunta `responde` recibe un texto no vacío distinto del texto de rechazo configurado, el sistema DEBE puntuarla como `acierto_recuperacion`. Límite declarado: no se mide el contenido de la respuesta, solo que no se rechazó (ver «Supuestos a confirmar»).

## R30
CUANDO se calcula el resumen de R13, el sistema DEBE contar las preguntas `sin_respuesta`, `error` y `rechazo_indebido` como fallos (aparecen en la lista de fallos), incluirlas en el denominador de su tipo de pregunta y NO contarlas como aciertos de recuperación ni como rechazos correctos.

## R31
CUANDO se calcula la proporción de aciertos de recuperación (R13, R22), el denominador DEBE ser el total de preguntas `responde`, incluidas las puntuadas `sin_respuesta`, `error` y `rechazo_indebido`.

## R32
SI `--top-k` está fuera del rango 1 a 20 (máximo del contrato `/search`) ENTONCES el sistema DEBE terminar con código distinto de 0 y un mensaje claro, sin enviar ninguna petición.

## R33
SI `--umbral-minimo-aciertos` está fuera del rango 0 a 1 ENTONCES el sistema DEBE terminar con código distinto de 0 y un mensaje claro, sin enviar ninguna petición.

## Trazabilidad con el acceptance original

- Criterio 1 (preguntas): R1, R2, R3, R6. Criterio 2 (manual): R4, R5. Criterio 3 (ejecución e informe): R15-R20, R25-R33. Criterio 4 (puntuación separada y con tests): R7-R14, R29-R31. Criterio 5 (supuesto de recalibración): R21 y `design.md` «Supuestos a confirmar».
