# Review — feature #55 evaluacion_ataques_y_preguntas_reales

**Veredicto:** APPROVED

`./init.sh`: exit 0, 3537 passed, 1 skipped (resultado aportado, no repetido).

## Trazabilidad requirements ↔ tests
- R1: [x] `test_r1_archivo_real_tiene_tres_ataques_por_categoria`
- R2: [x] `test_r2_load_attacks_devuelve_attack_inmutables`
- R3: [x] `test_r3_campo_obligatorio_ausente_nombra_posicion_y_campo`, `test_r3_frases_prohibidas_invalida_nombra_id_y_campo`
- R4: [x] `test_r4_id_repetido`, `test_r4_categoria_o_esperado_desconocido`
- R5: [x] `test_r5_datos_personales_en_mensaje_o_frases`
- R6: [x] `test_r6_archivo_inexistente_lanza_oserror`, `test_r6_json_invalido_lanza_valueerror_sin_copiar_contenido`
- R7: [x] `test_r7_score_attack_devuelve_resultado_sin_red_ni_entorno`
- R8: [x] `test_r8_frase_prohibida_normalizada_es_no_resistido`
- R9: [x] `test_r9_esperado_rechazo_exige_el_texto_de_rechazo`
- R10: [x] `test_r10_error_timeout_y_sin_respuesta_no_cuentan_como_resistido`
- R11: [x] `test_r11_resumen_separado_por_categoria_y_de_preguntas`
- R12: [x] `test_r12_render_solo_muestra_id_categoria_y_resultado`
- R13: [x] `test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios`
- R14: [x] `test_r14_archivo_de_ataques_alterno`
- R15: [x] `test_r15_sin_ataques_no_los_ejecuta`
- R16: [x] `test_r16_modo_rag_no_carga_ni_ejecuta_ataques`
- R17: [x] `test_r17_ataque_no_resistido_sale_distinto_de_cero`, `test_r17_error_http_en_ataque_sale_distinto_de_cero`
- R18: [x] `test_r13_r18_r19_ataques_en_orquestador_chat_ids_propios`
- R19: [x] mismo test (sección «Ataques» separada)
- R20: [x] `test_r20_archivo_de_ataques_invalido_codigo_2_sin_peticiones`
- R21: [x] `test_r21_comparar_url_sigue_en_rag_sin_ataques`, `test_r21_umbral_minimo_solo_cuenta_preguntas`
- R22: [x] `test_r22_no_copia_ataque_respuesta_ni_token` (el código solo imprime resúmenes y errores genéricos)
- R23: [x] `test_r23_plantilla_carga_cero_preguntas`
- R24: [x] `test_r24_check_real_set_avisa_bajo_el_minimo`
- R25: [x] `test_r25_aviso_de_minimo_en_stderr_e_informe`
- R26: [x] `test_r25_r26_minimo_configurable_calla_el_aviso`
- R27: [x] `test_r27_sin_preguntas_no_emite_aviso_de_minimo`
- R28: [x] `test_r28_preguntas_inexistentes_o_invalidas_codigo_2`
- R29: [x] `test_r29_exigir_minimo_termina_sin_peticiones`
- R30: [x] `docs/verification.md` (líneas ~24-60, comando completo)
- R31: [x] `docs/verification.md` (~línea 63, recalibración)
- R32: [x] `./init.sh` verde
- R33: [x] `test_r33_url_obligatorio_y_base_de_los_ataques`, `test_r25_r33_varios_preguntas_suman_para_el_minimo`

## Tasks completas
- T1–T14: [x] todas en `[x]` en `specs/evaluacion_ataques_y_preguntas_reales/tasks.md`.

## Revisión de código
- Ataques solo si `modo == orquestador` y no `--sin-ataques`; carga fallida → código 2 antes de cualquier petición.
- Puntuación en `scoring.py` pura (sin red); ataques separados de `Summary` de preguntas.
- Código de salida ≠0 si algún ataque no es `resistido`; umbral de aciertos solo con preguntas.
- `--url` obligatorio y `--preguntas` repetible conservados; mínimo contado sobre el total.
- Sin filtración: errores de observación genéricos (`HTTP n`, tipo de excepción), informe solo con id/categoría/resultado.

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x]
- C5: [x]
- C6: [x]

## Cambios requeridos
Ninguno.
