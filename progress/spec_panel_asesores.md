# Blocker parcial — #29 panel_asesores

**Solo afecta a R13 (listar casos) y a las tasks T9–T10.** R1–R12 y R14–R15 se
pueden implementar ya.

**Problema.** Handover no publica ninguna ruta de lectura de casos
(`contracts/CONTRATOS.md` solo tiene `assign`, `authorize`, `close`,
`client-message`, `check-timeouts` por caso). El orquestador no conoce estado ni
asesor (`case_links` = `case_id → contact_id`). Listar "solo los casos que las
reglas permiten" exige una ruta nueva y, según `docs/architecture.md` §3.2, un
cambio de contrato va en su propia feature.

**Pregunta concreta.** ¿Se registra la feature de contrato
`contrato_listar_casos_asesor` (handover `GET /cases?advisor_id=<id>`) y se añade
a `depends_on` de #29?

**Opción recomendada.** Sí, antes de implementar #29, con los defaults de
`specs/panel_asesores/design.md` §Bloqueo: campos `case_id`, `status`,
`created_at`, `actions`; sin datos de contacto ni mensajes; asesor no registrado
→ lista vacía; `CASE_LIST_LIMIT=50`. Alternativa: implementar #29 sin R13
(formularios por `case_id`, como en Telegram) y cerrar R13 después.
