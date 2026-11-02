# Spec review — #21 panel_administracion (2ª revisión)

**Veredicto:** APPROVED

## Bloqueantes de la 1ª revisión

1. **Límite de intentos de login — resuelto.**
   - `requirements.md` R11 (líneas 75–82): SI/ENTONCES, por `username` normalizado o
     por IP, `ADMIN_LOGIN_MAX_ATTEMPTS`/`ADMIN_LOGIN_WINDOW_MINUTES`, `429` con el
     mensaje de R2, **antes** de `verify_password`, sin sesión, bloqueo temporal y
     reinicio al acertar.
   - `design.md`: tabla persistente `admin_login_attempts` con índices (l. 38–42),
     métodos de repositorio (l. 56–58), algoritmo que no registra el intento
     bloqueado (l. 75–87), IP desde `request.client.host` y `X-Forwarded-For` solo
     con `ADMIN_TRUST_PROXY_HEADERS=true` (l. 88–90), variables en Config (l. 122–124).
   - `tasks.md`: variables y tabla en T1, lógica en T3, tests en T4 (N fallos por
     username/IP → 429, espía en `verify_password`, ventana con reloj, reinicio,
     XFF ignorado por defecto).
2. **R3 frente a `/admin/static/admin.css` — resuelto.** R3 (l. 26–27) ya incluye
   `GET /admin/static/admin.css` como excepción, igual que el design (l. 101) y T4,
   que lo prueba sin cookie → `200`.

## Coherencia requirements / tasks / acceptance

- `acceptance` tiene 6 criterios; la tabla de cobertura (`requirements.md` l. 84–93)
  ya usa la misma numeración y cubre los 6 (el 5 = R11).
- Las tasks T1–T6 están todas en `[ ]` y entre todas cubren R1–R11 (R6 en T6; R7 y R9 en T5).

## No bloqueante

- R11 lleva dos `DEBE` (el 429 y el reinicio del contador). Se acepta tal como está
  porque los dos se prueban en T4. Si se quiere EARS estricto, el reinicio se puede
  pasar a un R12 con CUANDO.
