# Implementación — evaluacion (#8)

Estado: implementado, `./init.sh` verde (565 tests). Pendiente de reviewer; no marcado `done`.

Archivos: `eval/scoring.py`, `eval/run_eval.py`, `eval/preguntas.json`, `eval/manual_ejemplo/manual_ejemplo.md`, `eval/tests/{conftest,test_preguntas,test_scoring,test_run_eval}.py`, `.env.example` (EVAL_SINK_PORT). `eval/resultados_*.md` ya estaba en `.gitignore`. Sin dependencias nuevas.

## Mapa R -> test
- R1,R2,R3: test_preguntas::test_r1_r2_r3_conteos_e_ids_unicos
- R4: test_preguntas::test_r4_manual_existe_y_es_texto
- R5: test_preguntas::test_r5_fragmento_esperado_en_manual
- R6: test_preguntas::test_r6_* (5 tests)
- R7: test_scoring::test_r7_scoring_sin_red_ni_entorno
- R8: test_r8_acierto_por_fragmento_normalizado / _por_chunk_id
- R9: test_r9_fallo_lista_vacia_y_sin_fragmento
- R10: test_r10_rechazo_correcto_rag_y_orquestador
- R11: test_r11_respuesta_inventada
- R12: test_r12_rechazo_indebido
- R13,R30,R31: test_r13_r30_r31_resumen
- R14: test_r14_proporcion_none_sin_preguntas_de_un_tipo
- R15: test_r15_informe_con_fallos_y_ninguno
- R16: test_run_eval::test_r16_* (cuerpo, RAG_TOP_K, defecto 5)
- R17,R26: test_r17_r25_r26_orquestador
- R18: test_scoring::test_r18_sin_respuesta; test_run_eval::test_r18_r28_sin_respuesta_continua
- R19,R27: test_r19_r27_r28_error_http_salida_distinta_de_cero_y_continua; test_r19_error_de_conexion
- R20: test_r16_r25_search_cuerpo_y_encabezado_r20_informe
- R21: test_r21_preguntas_alternas_repetible
- R22: test_r22_umbral_minimo
- R23: test_r23_sin_token_no_envia_nada
- R24: test_r16_r25_... (informe y stdout/stderr sin token)
- R25: test_r16_r25_... y test_r17_r25_r26_orquestador
- R28: test_r18_r28_*, test_r19_r27_r28_*
- R29: test_scoring::test_r29_orquestador_responde_no_rechazo_es_acierto
- R32: test_r32_top_k_fuera_de_rango
- R33: test_r33_umbral_fuera_de_rango

## Notas
- `--help` documenta la carga del manual con `scripts/cargar_manual.py`.
- `test_reply_sink_real_captura_send` abre un socket solo en 127.0.0.1 (puerto efímero); no hay red externa.
