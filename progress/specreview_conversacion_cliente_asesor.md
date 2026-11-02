# Spec review — conversacion_cliente_asesor (feature #16)

**Veredicto:** SPEC_APPROVED

Revisión nocturna del 2026-11-01. Fuentes:
- `specs/conversacion_cliente_asesor/{requirements,design,tasks}.md`, contra el acceptance de la #16 (A1-A14).
- Los specs de la #13 (C5), la #14, la #15, la #17 y la #18.
- `contracts/CONTRATOS.md`: líneas `Llama` de `close` (l. 278), `authorize` (l. 382) y `client-message` (l. 421), y S13.
- El código actual:
  - orchestrator: `domain.py:306-355`, `adapters/handover.py`, `adapters/gateway.py:43-51` y `adapters/repository.py`;
  - handover: `domain.py:336-358`, `adapters/gateway.py:43-51`, `adapters/repository.py:62-69` y `tests/conftest.py`.

No se ejecutaron tests: es una revisión de spec.

## Cambios del informe anterior
1. **T25/fake del gateway: resuelto.** `FakeGatewayClient(fail, fail_for)` es aditivo (design §2 y §3.7, T4b). T25 usa `fail_for={100}`, así que la aserción sobre el chat 111 es implementable.
2. **A12: resuelto.** R59 y D9 dicen que el aviso al cliente solo sale con `/cerrar`, y T74 lo prueba. Coincide con `close_case` de handover, que no envía nada.
3. **`/cerrar` frente a la ruta HTTP y la #13: resuelto.**
   - La línea `Llama` de `authorize` ya nombra `/cerrar` (CONTRATOS.md:382).
   - Un caso `closed` sigue la opción (c), alineada con C5: R60-R62, texto propio, sin `advisor_forbidden`, y nunca se llama a `close` (R22).
   - El código de `reply_to_case` (`domain.py:332-333`, `CaseClosed` sin registro) casa con R60/R62.
   - La divergencia con S8 está documentada en design §3.3.
4. **§12 de `docs/proyecto.md`: resuelto.** Design §11 recoge las dos dudas: bot único y Ley 1581, con la ampliación del tratamiento de datos.
5. **Consecuencias no documentadas: resuelto.**
   - C1-C4 están documentadas en §7 y §9.2.
   - Carreras y conexión compartida remiten a D10 de la #14 y a la #18. El candado está en `PostgresRepository._run` (`repository.py:139,151-152`) y `get_contact_last_case` lo hereda.
   - Los huérfanos quedan cubiertos por la #17 (opción C + procedimiento A), con el riesgo residual de reenvío explicado.
6. **Marcas de D1 en R1-R4: resuelto.**
7. **T65: resuelto.** Ahora es incondicional (`requests == []`, `denials == []` y `notifications` sin cambios). Los atributos existen en `FakeCaseRepository`.

## Comprobaciones
- **Cobertura:** cada criterio A1-A14 tiene al menos un R (tabla final de `requirements.md`), y cada R1-R62 tiene un test en `tasks.md`. R55 y R56 se cubren con los parametrizados de T10; R59 con T74.
- **EARS:** un solo `DEBE`/`NO DEBE` por R, con el servicio indicado y sin verbos blandos.
- **Coherencia con el código:**
  - Los fakes y atributos que usan los tests existen o se añaden de forma aditiva: `authorized`, `assigned`, `authorize_error`, `fail_authorize`, el `fail_for` de handover y `ADVISORS = [111, 222, 333]`.
  - `MessageRequest.telegram_user_id: int` admite 0 y negativos, así que T20 es implementable.
- **Diseño:**
  - Respeta las 3 capas: el parser es puro y el IO va por adaptadores.
  - El SQL es parametrizado y no crea tablas ni dependencias nuevas.
  - No toca `contracts/` y el orquestador no lee `ADVISOR_CHAT_IDS`.
  - Tiene 10 alternativas descartadas y la sección «Supuestos a confirmar».
- **Tasks:** todas en `[ ]`, en orden lógico y con sus R.
- **Nada peligroso:** no borra datos, no usa red en los tests y no toca archivos fuera del repo.

## Notas no bloqueantes
- La `description` de la #16 en `feature_list.json` aún dice «PENDIENTE … alinear con C5», pero ya está hecho. El leader puede limpiarla.
- Los ids de las tasks no van en orden (T74 aparece antes de T71-T73). Es solo editorial.
