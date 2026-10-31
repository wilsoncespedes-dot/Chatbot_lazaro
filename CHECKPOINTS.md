# CHECKPOINTS — Evaluación del estado final

> En sistemas multi-agente no se evalúa el camino, se evalúa el destino.
> Estos son los checkpoints objetivos que un juez (humano o IA) puede usar
> para decidir si el proyecto está sano.

## C1 — El arnés está completo

- [ ] Existen los archivos base: `AGENTS.md`, `init.sh`, `feature_list.json`,
      `progress/current.md`, `docs/proyecto.md`.
- [ ] Existen los docs: `docs/architecture.md`, `docs/conventions.md`,
      `docs/verification.md`, `docs/specs.md`.
- [ ] `./init.sh` termina con exit code 0.

## C2 — El estado es coherente

- [ ] Como mucho una feature en `in_progress` en `feature_list.json`.
- [ ] Toda feature `done` tiene tests asociados que pasan.
- [ ] `progress/current.md` está vacío o describe la sesión activa.

## C3 — El código respeta la arquitectura

- [ ] Solo existen los servicios y carpetas previstos en
      `docs/architecture.md` §1 (o los que una feature justificó en su `design.md`).
- [ ] Ningún servicio importa código de otro servicio; lo compartido está
      solo en `contracts/lazaro_contracts`.
- [ ] Toda ruta entre servicios está en `contracts/CONTRATOS.md`.
- [ ] Toda dependencia nueva está en el `requirements.txt` del servicio, con
      versión acotada, y aparece en el `design.md` de su feature.
- [ ] Ninguna dependencia es GPL/AGPL. Todo código copiado está en
      `THIRD_PARTY_NOTICES.md` con su licencia (MIT o Apache 2.0).
- [ ] No hay secretos en el código ni en git: `.env` no está trackeado y
      toda variable nueva está en `.env.example`.
- [ ] No hay `print()` de debug, `eval`/`exec`, SQL concatenado con texto del
      usuario, ni TODOs sin contexto.

## C4 — La verificación es real

- [ ] Cada servicio existente tiene tests en `services/<servicio>/tests/`.
- [ ] Los tests usan adaptadores falsos: ninguno llama a Telegram, al
      proveedor de IA ni a una base de datos real (salvo los marcados
      `integration`).
- [ ] `python -m pytest` muestra > 0 tests y todos verdes (a partir de la feature 2).
- [ ] Las pruebas de seguridad obligatorias de `docs/verification.md` que ya
      aplican existen y pasan.

## C5 — La sesión se cerró bien

- [ ] No hay archivos sin trackear sospechosos (`*.tmp`, `.env`, cachés
      fuera del `.gitignore`).
- [ ] `progress/history.md` tiene una entrada por la última sesión.
- [ ] La última feature trabajada está reflejada en su estado correcto.

## C6 — Spec Driven Development

- [ ] Toda feature `sdd: true` en `spec_ready`, `in_progress` o `done` tiene
      `specs/<name>/` con `requirements.md`, `design.md`, `tasks.md`.
- [ ] `requirements.md` usa EARS estricto (ver `docs/specs.md`).
- [ ] `design.md` lista dependencias nuevas y «Supuestos a confirmar».
- [ ] Toda feature `done` tiene todas sus tasks en `[x]`.
- [ ] Cada `R<n>` está cubierto por al menos un test concreto.

---

**Cómo usar este archivo:** el `reviewer` (`.claude/agents/reviewer.md`)
recorre cada checkbox, marca `[x]` o `[ ]`, y rechaza el cierre si quedan
boxes vacíos en C1-C6 que apliquen a la feature.
