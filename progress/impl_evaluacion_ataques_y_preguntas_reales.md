# Implementación — evaluacion_ataques_y_preguntas_reales (#55)

## Resumen

- `eval/scoring.py`: ataques (`Attack`, `AttackResult`, `AttackSummary`,
  `load_attacks`, `score_attack`, `summarize_attacks`, `render_attacks`) y
  `check_real_set`. `Summary` de preguntas no cambia.
- `eval/ataques.json`: 13 ataques, al menos 3 por categoría, sin datos reales.
- `eval/preguntas_reales.plantilla.json`: plantilla con lista vacía e
  instrucciones.
- `eval/run_eval.py`: flags `--ataques`, `--sin-ataques`,
  `--minimo-preguntas`, `--exigir-minimo`; ataques solo en modo orquestador
  con chat ids propios; aviso de mínimo solo con `--preguntas`; sección
  «Ataques» separada y código de salida propio. `--url`, `--preguntas`
  repetible, `--comparar-url` y `--umbral-minimo-aciertos` se conservan.
- `eval/tests/test_attacks_scoring.py` y `eval/tests/test_run_eval_attacks.py`
  nuevos; tests de modo orquestador existentes usan `--sin-ataques`.
- `docs/verification.md`: sección manual de evaluación, comandos, plantilla y
  recalibración de `RAG_SIMILARITY_THRESHOLD`.
- T14 queda pendiente de verificación final; el mapa R→test está documentado abajo.

## Trazabilidad

- R1 → `eval/tests/test_attacks_scoring.py::test_r1_archivo_real_tiene_tres_ataques_por_categoria`
- R2 → `eval/tests/test_attacks_scoring.py::test_r2_load_attacks_devuelve_attack_inmutables`
- R3 → `eval/tests/test_attacks_scoring.py::test_r3_campo_obligatorio_ausente_nombra_posicion_y_campo`, `test_r3_frases_prohibidas_invalida_nombra_id_y_campo`
- R4 → `eval/tests/test_attacks_scoring.py::test_r4_id_repetido`, `test_r4_categoria_o_esperado_desconocido`
- R5 → `eval/tests/test_attacks_scoring.py::test_r5_datos_personales_en_mensaje_o_frases`
- R6 → `eval/tests/test_attacks_scoring.py::test_r6_archivo_inexistente_lanza_oserror`, `test_r6_json_invalido_lanza_valueerror_sin_copiar_contenido`
- R7 → `eval/tests/test_attacks_scoring.py::test_r7_score_attack_devuelve_resultado_sin_red_ni_entorno`
- R8 → `eval/tests/test_attacks_scoring.py::test_r8_frase_prohibida_normalizada_es_no_resistido`
- R9 → `eval/tests/test_attacks_scoring.py::test_r9_esperado_rechazo_exige_el_texto_de_rechazo`
- R10 → `eval/tests/test_attacks_scoring.py::test_r10_error_timeout_y_sin_respuesta_no_cuentan_como_resistido`
- R11 → `eval/tests/test_attacks_scoring.py::test_r11_resumen_separado_por_categoria_y_de_preguntas`
- R12 → `eval/tests/test_attacks_scoring.py::test_r12_render_solo_muestra_id_categoria_y_resultado`
- R13 → `eval/tests/test_run_eval_attacks.py::test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios`
- R14 → `eval/tests/test_run_eval_attacks.py::test_r14_archivo_de_ataques_alterno`
- R15 → `eval/tests/test_run_eval_attacks.py::test_r15_sin_ataques_no_los_ejecuta`
- R16 → `eval/tests/test_run_eval_attacks.py::test_r16_modo_rag_no_carga_ni_ejecuta_ataques`
- R17 → `eval/tests/test_run_eval_attacks.py::test_r17_ataque_no_resistido_sale_distinto_de_cero`, `test_r17_error_http_en_ataque_sale_distinto_de_cero`
- R18 → `eval/tests/test_run_eval_attacks.py::test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios`
- R19 → `eval/tests/test_run_eval_attacks.py::test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios`
- R20 → `eval/tests/test_run_eval_attacks.py::test_r20_archivo_de_ataques_invalido_codigo_2_sin_peticiones`
- R21 → `eval/tests/test_run_eval_attacks.py::test_r21_comparar_url_sigue_en_rag_sin_ataques`, `test_r21_umbral_minimo_solo_cuenta_preguntas`
- R22 → `eval/tests/test_run_eval_attacks.py::test_r22_no_copia_ataque_respuesta_ni_token`
- R23 → `eval/tests/test_attacks_scoring.py::test_r23_plantilla_carga_cero_preguntas`
- R24 → `eval/tests/test_attacks_scoring.py::test_r24_check_real_set_avisa_bajo_el_minimo`
- R25 → `eval/tests/test_run_eval_attacks.py::test_r25_aviso_de_minimo_en_stderr_e_informe`, `test_r25_r33_varios_preguntas_suman_para_el_minimo`
- R26 → `eval/tests/test_run_eval_attacks.py::test_r25_r26_minimo_configurable_calla_el_aviso`, `test_r25_r33_varios_preguntas_suman_para_el_minimo`
- R27 → `eval/tests/test_run_eval_attacks.py::test_r27_sin_preguntas_no_emite_aviso_de_minimo`
- R28 → `eval/tests/test_run_eval_attacks.py::test_r28_preguntas_inexistentes_o_invalidas_codigo_2`
- R29 → `eval/tests/test_run_eval_attacks.py::test_r29_exigir_minimo_termina_sin_peticiones`
- R30 → `docs/verification.md`, sección «Evaluación del bot (manual, no CI)» (comando completo con `--url`, `--modo orquestador`, `--preguntas`, `--ataques`, `--minimo-preguntas`)
- R31 → `docs/verification.md`, subsección «Recalibrar `RAG_SIMILARITY_THRESHOLD`»
- R32 → `./init.sh` (pendiente de la ejecución de Claude; T14)
- R33 → `eval/tests/test_run_eval_attacks.py::test_r33_url_obligatorio_y_base_de_los_ataques`, `test_r25_r33_varios_preguntas_suman_para_el_minimo`

## Verificación

`bash ./init.sh`: exit 0, 3537 passed, 1 skipped y 2 avisos de deprecación.
T1–T14 completas; queda pendiente la revisión de código Claude.
