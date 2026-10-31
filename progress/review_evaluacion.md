# Review — feature 8 (evaluacion)

**Veredicto:** APPROVED

`./init.sh` verde (565 tests pasan, modo nocturno). Sin dependencias nuevas; `eval/` no importa código de servicios (solo `lazaro_contracts`).

## Trazabilidad requirements ↔ tests
- R1, R2, R3: [x] `test_preguntas::test_r1_r2_r3_conteos_e_ids_unicos`
- R4: [x] `test_r4_manual_existe_y_es_texto`
- R5: [x] `test_r5_fragmento_esperado_en_manual`
- R6: [x] `test_r6_*` (5 tests)
- R7: [x] `test_scoring::test_r7_scoring_sin_red_ni_entorno` (scoring.py solo importa json, dataclasses, datetime, pathlib, typing)
- R8: [x] `test_r8_*` (2)
- R9: [x] `test_r9_fallo_lista_vacia_y_sin_fragmento`
- R10: [x] `test_r10_rechazo_correcto_rag_y_orquestador`
- R11: [x] `test_r11_respuesta_inventada`
- R12: [x] `test_r12_rechazo_indebido`
- R13, R30, R31: [x] `test_r13_r30_r31_resumen`
- R14: [x] `test_r14_proporcion_none_sin_preguntas_de_un_tipo`
- R15: [x] `test_r15_informe_con_fallos_y_ninguno`
- R16: [x] `test_r16_r25_search_cuerpo_...`, `test_r16_top_k_por_defecto_*`
- R17, R26: [x] `test_r17_r25_r26_orquestador`
- R18: [x] `test_scoring::test_r18_sin_respuesta`, `test_run_eval::test_r18_r28_sin_respuesta_continua`
- R19, R27: [x] `test_r19_r27_r28_error_http_...` (401, 500), `test_r19_error_de_conexion`
- R20: [x] `test_r16_r25_..._r20_informe`
- R21: [x] `test_r21_preguntas_alternas_repetible`
- R22: [x] `test_r22_umbral_minimo`
- R23: [x] `test_r23_sin_token_no_envia_nada`
- R24: [x] `test_r16_r25_...` (informe y stdout/stderr sin el token)
- R25: [x] `test_r16_r25_...` (/search), `test_r17_r25_r26_orquestador` (/messages)
- R28: [x] `test_r18_r28_*`, `test_r19_r27_r28_*`
- R29: [x] `test_r29_orquestador_responde_no_rechazo_es_acierto`
- R32: [x] `test_r32_top_k_fuera_de_rango`
- R33: [x] `test_r33_umbral_fuera_de_rango`

## Tasks completas
- T1 a T14: [x] todas en `[x]` en `specs/evaluacion/tasks.md`.

## Revisión de código
- `eval/scoring.py` es lógica pura. La división por cero está evitada con `_ratio`. Los fallos incluyen `sin_respuesta`, `error` y `rechazo_indebido`, y el denominador es el total por tipo.
- `eval/run_eval.py` valida el token, `--top-k` y el umbral antes de enviar ninguna petición. Envía `X-Service-Token`, usa un `chat_id` único por pregunta y continúa tras fallos. Sale con código distinto de 0 si hay `error` o si no se alcanza el umbral. El token nunca se imprime.
- `.env.example` incluye `EVAL_SINK_PORT`. `.gitignore` ya excluye `eval/resultados_*.md`.
- Los `print()` de `run_eval.py` son la salida normal del CLI y no son de depuración.
- Observación no bloqueante: `.claude/settings.json` aparece modificado en el árbol. No pertenece a esta feature, y el leader o el modo nocturno deben confirmar que es intencional.
- Observación no bloqueante: `design.md` menciona un posible `eval/requirements.txt`. Como `eval/` no es un servicio y no se añade ninguna dependencia, no se exige.

## Checkpoints
- C1: [x]
- C2: [x] (solo #8 en curso)
- C3: [x] (sin imports entre servicios, sin secretos, variable nueva en `.env.example`, sin GPL)
- C4: [x] (cliente falso con `MockTransport`; el único socket abierto es local en 127.0.0.1)
- C5: [x] (`progress/history.md` y el estado final de la feature los gestiona el leader al cerrar)
- C6: [x]

## Cambios requeridos
Ninguno.
