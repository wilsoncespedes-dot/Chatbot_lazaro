# Requirements — validacion_config_asesores

Feature #10. Servicio: solo `handover`. Hace que una `ADVISOR_CHAT_IDS` mal escrita impida el
arranque en lugar de descartar entradas en silencio, y deja en el log de arranque cuántos
asesores hay configurados (nunca sus ids).

Esta feature **modifica R23 de la #7** (`specs/traspaso_asesor/requirements.md`), con el
cambio aceptado por el humano el 2026-10-31: la parte «las entradas no numéricas se descartan»
queda sustituida por R3-R4 de este spec; la parte «las entradas vacías se descartan» se conserva
(R2). El resto de R23 (`HANDOVER_TIMEOUT_SECONDS`, `HANDOVER_TIMEOUT_REPLY`) no cambia. Ver
design.md, «Cambio sobre R23 de la #7».

Terminología: una **entrada** es cada trozo de `ADVISOR_CHAT_IDS` separado por comas, sin los
espacios que la rodean. Su **posición** se cuenta desde 1 sobre todos los trozos, incluidos los
vacíos (supuesto S1, design.md).

## Lectura de ADVISOR_CHAT_IDS (handover, `Settings`)

## R1
CUANDO se construye `Settings` de handover, el sistema DEBE quitar los espacios que rodean cada
entrada de `ADVISOR_CHAT_IDS` antes de validarla (p. ej. `" 111 , 222 "` → `[111, 222]`).

## R2
CUANDO se construye `Settings` de handover y una entrada de `ADVISOR_CHAT_IDS` está vacía (comas
seguidas, coma inicial o final, solo espacios o solo comas), el sistema DEBE ignorarla sin
lanzar error.

## R3
SI una entrada no vacía de `ADVISOR_CHAT_IDS` no es un entero (supuesto S2 sobre qué es un
entero) ENTONCES el sistema DEBE hacer que `Settings()` lance `pydantic.ValidationError`.

## R4
SI `Settings()` lanza el error de R3 ENTONCES el mensaje del error DEBE indicar la posición y el
valor de la primera entrada no válida.

## R5
SI dos entradas de `ADVISOR_CHAT_IDS` representan el mismo entero (supuesto S3) ENTONCES el
sistema DEBE hacer que `Settings()` lance `pydantic.ValidationError`.

## R6
SI `Settings()` lanza el error de R5 ENTONCES el mensaje del error DEBE indicar que hay un id
repetido y las posiciones de sus dos primeras apariciones (supuesto S4: sin el id).

## R7
CUANDO se construye `Settings` de handover y una entrada de `ADVISOR_CHAT_IDS` es un entero
negativo (grupo o canal de Telegram), el sistema DEBE aceptarla como id de asesor.

## R8
SI `Settings()` lanza un error de validación por `ADVISOR_CHAT_IDS` ENTONCES el texto del error
NO DEBE contener ninguna entrada de la lista distinta de la entrada no válida que informa R4.
Derivado del criterio 4 («no sus ids»); supuesto S5, a confirmar por el humano. (La entrada no
válida sí aparece, por R4, aunque contenga dígitos de un id: p. ej. `'987654321x'`.)

## Arranque (handover, `create_app`)

## R9
SI `create_app()` se llama sin `settings` y `ADVISOR_CHAT_IDS` no es válida según R3 o R5
ENTONCES el sistema DEBE propagar el `pydantic.ValidationError` sin devolver ninguna app.

## R10
CUANDO `create_app` construye la app, el sistema DEBE registrar en el log, a nivel `INFO`, el
evento `advisors_configured` con el número de asesores configurados.

## R11
CUANDO `create_app` construye la app y la lista de asesores está vacía, el sistema DEBE
registrar en el log, a nivel `WARNING`, el evento `no_advisors_configured`.

## R12
MIENTRAS la lista de asesores esté vacía, el sistema DEBE dejar que `create_app` devuelva la
app (el servicio arranca).

## R13
El sistema NO DEBE incluir ningún id de asesor en los registros de log que emite `create_app`
al construir la app.

## R14
MIENTRAS la lista de asesores esté vacía por contener solo entradas vacías, el sistema DEBE
responder a `POST /handover` con `{"status": "no_advisors", ...}` sin llamar a `POST /send`
(R8 de la #7 sin cambios).

## R15
CUANDO el proceso de handover arranca importando `handover.main` (como hace
`uvicorn handover.main:app`) sin ninguna configuración de logging previa, el sistema DEBE
escribir el registro `advisors_configured` de R10 en la salida de error estándar del proceso.
(Hace que el criterio 4 se cumpla en el arranque real, no solo bajo `caplog`; ver design.md,
«Logging del servicio».)

## Fuera de alcance

Comprobar que el bot puede escribir a cada chat de `ADVISOR_CHAT_IDS` (cada aviso fallido ya
queda registrado con `delivered = false`; comprobarlo antes exigiría una ruta nueva en el
gateway). Cambios en `contracts/`, en otros servicios o en el log `advisor_notice_failed` de
`domain.py` (no es un log de arranque).

## Trazabilidad con el `acceptance` de feature_list.json

| Criterio (orden) | Requirements |
|------------------|--------------|
| 1. Entrada no vacía debe ser entero; error con posición y valor; `create_app()` no crea la app | R1, R3, R4, R9 |
| 2. Entradas vacías se siguen ignorando | R2 |
| 3. Lista vacía: arranca, aviso `no_advisors_configured`, `no_advisors` sin cambios | R11, R12, R14 |
| 4. Log de arranque con el número de asesores, no sus ids | R10, R13, R15, R8 |
| 5. (Humano) id repetido → error de validación, no arranca | R5, R6, R9 |
| 6. (Humano) negativos válidos | R7 |
| 7. (Humano) cambio de R23 de la #7 y de su test | R2, R3 (ver design.md, «Cambio sobre R23 de la #7») |
| 8. Fuera de alcance: comprobar escritura a cada chat | sección «Fuera de alcance» |
| 9. Tests listados | tasks.md: no numérico (R3), duplicado (R5), solo comas (R2), lista vacía con aviso (R11), negativos (R7), espacios (R1), `create_app` falla (R9), log sin ids (R13); además log visible en el arranque real (R15) |
