# Spec review — #29 panel_asesores (segunda pasada)

**Veredicto:** APPROVED

## Bloqueantes anteriores: resueltos

1. **Dependencia del listado de casos.** `feature_list.json` registra #33
   `contrato_listar_casos_asesor` (`pending`, `sdd: true`, deps `[14, 17]`). Su
   acceptance incluye `CONTRATOS.md`, los modelos, los campos mínimos y
   `CASE_LIST_LIMIT=50`. #29 tiene `"dependencies": [14, 16, 20, 21, 33]`.
   `design.md` §«Dependencia #33» y `tasks.md` T9–T10 esperan a #33 en lugar de
   decir «BLOQUEADO». Ya no aparece `depends_on`. #29 no cambia `contracts/` ni
   `CONTRATOS.md`: solo consume la ruta mediante `list_cases` (T9).
2. **CSRF.** `design.md:24`: solo `LoginRequired` redirige según el path, y
   `CsrfInvalid` siempre devuelve `403`. Coincide con R6
   (`requirements.md:58-59`), T7 y T8 («CSRF ausente/erróneo → 403 sin
   llamadas»).

## No bloqueante

- `requirements.md:15-19`, `:99` y `:127` todavía dicen «bloqueado/Bloqueo
  parcial» para R13. El sentido es correcto (depende de una feature previa), así
  que es editorial. Se puede cambiar a «depende de #33» al empezar la
  implementación.
- Al empezar #29, el leader comprueba que #33 esté `done` antes de T9–T10.
