# Spec review — #23 bootstrap_administrador

**Veredicto:** APPROVED

Sin bloqueos materiales. Los 3 criterios de `acceptance` están cubiertos (R1–R10),
cada `R<n>` es verificable, las tasks T1–T9 están en `[ ]` y entre todas cubren R1–R10.
`design.md` respeta las 3 capas y no añade dependencias, rutas ni variables nuevas.

## Puntos evaluados

- **Concurrencia de «rechaza si existe admin» (R6):** la garantía no es atómica.
  Dos ejecuciones simultáneas con *usernames distintos* pueden crear dos admins
  (con el mismo username, `profiles.username UNIQUE` → `UsernameTaken` → R8).
  No bloquea: el design lo descarta de forma explícita (Alternativas descartadas),
  y quien puede ejecutarlo ya tiene `docker compose exec` y `DATABASE_URL`,
  es decir, ya puede escribir en `profiles`. No hay escalada de privilegios.
  *Sugerencia (no bloqueante):* el paso 4 (comprobar) va antes de la doble
  `getpass`, así que la ventana dura lo que tarde una persona en escribir.
  Volver a llamar a `list_profiles()` justo antes de `create_profile` la
  reduce a milisegundos sin tocar `Repository` ni el esquema.
- **Ejecución en el contenedor con `DATABASE_URL`:** correcto. El Dockerfile copia
  `orchestrator/` en `/app` (WORKDIR), así que `python -m orchestrator.bootstrap_admin`
  se resuelve. `docker-compose.yml` inyecta `.env` (`env_file`) y `Settings()`
  lee `DATABASE_URL`. `PostgresRepository._connection()` crea el esquema
  (`CREATE TABLE IF NOT EXISTS profiles…`) en el primer uso, así que también
  funciona en una instalación vacía. R9 cubre el caso de `DATABASE_URL` vacía.
- **Tests/config:** cada R tiene una task de test (T2–T8). R5 se comprueba en
  `out`, `err` y `caplog` en todos los caminos, también cuando falla el
  repositorio. R6 compara los perfiles, hash incluido. R9 usa un monkeypatch
  que falla si se instancia `PostgresRepository`. Config: reutiliza
  `password_hash_iterations`, `profile_password_min_length` y `database_url`,
  que ya existen; no hace falta tocar `config.py` ni `.env.example`.

## Notas no bloqueantes
- R4 lleva dos `DEBE` (salida con 2 / no usar el entorno). Mejor partirlo en dos
  requisitos. Los dos ya tienen test en T3.
- La captura de «cualquier otra excepción del repositorio» (design, flujo) tiene
  que cubrir también `list_profiles()` (paso 4), no solo `create_profile`. Ahí
  saltan los fallos de conexión.
