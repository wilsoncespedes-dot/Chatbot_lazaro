# Spec review — #20 verificacion_cuentas

**Veredicto:** APPROVED

Alcance revisado: `specs/verificacion_cuentas/*`, acceptance de #20 en
`feature_list.json`, `docs/architecture.md`.

## Comprobaciones clave
- **Cobertura:** los 5 criterios de acceptance quedan cubiertos (R1–R10); tasks
  T1–T6 en `[ ]`, ordenadas y cubren todos los `R<n>`.
- **Credenciales:** PBKDF2-SHA256 600k con sal de 16 bytes, `hmac.compare_digest`,
  sin hash ni clave en respuestas/filas/logs (R3, `Profile` sin hash). Correcto.
- **Tokens:** `token_urlsafe(32)`, solo SHA-256 en BD, TTL 15 min configurable,
  consumo atómico con `used_at IS NULL` (un solo ganador también entre procesos),
  fallo de `UNIQUE` → rollback sin consumir. Mismo `link_failed_reply` en todos los
  errores (R7) → no revela si el perfil existe. El token nunca lo envía el bot;
  se desvía antes de `add_message`/RAG/LLM/traspaso (R9).
- **Rutas internas:** `POST /profiles` y `/profiles/{id}/link-token` quedan tras el
  middleware `X-Service-Token` (arquitectura §3.8, R10). No son rutas entre
  servicios, así que modelos locales sin entrada en `CONTRATOS.md` no violan §3.2.
- **Dependencias:** ninguna nueva (stdlib). SQL parametrizado. Config por env con
  defaults en `.env.example`.

## Notas no bloqueantes (para el implementer)
1. El desvío de `/start <token>` ocurre antes de `add_message`: asegurar que la
   deduplicación por id de mensaje (arquitectura §3.6) sigue aplicándose, para que
   un reintento de Telegram no responda `link_failed_reply` tras un vínculo correcto.
2. El log `account_link` no debe incluir `username` ni `profile_id` cuando falla
   (solo `result` y `contact_id`, como dice el design).
3. Validar `PASSWORD_HASH_ITERATIONS ≥ 100000` y `LINK_TOKEN_TTL_MINUTES` 1–1440 en
   `config.py` (fallo al arrancar si se sale del rango).
