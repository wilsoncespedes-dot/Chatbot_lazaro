# Design — preguntas_seguimiento (#64)

- `previous_question(contact, text, settings, adapters)`: `last_messages(contact.id, 6)`
  de más reciente a más antiguo; salta los mensajes no `user` y los iguales al
  actual (ya guardado); el primero restante vale si está dentro de la ventana.
  Usa el historial del contacto, con o sin sesión: es el mismo texto que ya se
  envió antes a embeddings, no se expone nada nuevo.
- Dos llamadas a `rag.search` (mensaje y combinada) → `merge_search_results`.
- `build_llm_prompt(..., previous=None)` añade `<pregunta_anterior>`;
  `_neutralize` neutraliza también `</pregunta_anterior`. El prompt del sistema
  indica usarla solo para entender la pregunta.
- Settings: `RAG_FOLLOWUP_ENABLED` (true), `RAG_FOLLOWUP_MAX_WORDS` (8),
  `RAG_FOLLOWUP_WINDOW_MINUTES` (30), documentados en `.env.example`.
