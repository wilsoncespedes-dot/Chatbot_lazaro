---
description: Confirma que revisaste los specs que el reviewer aprobó en modo nocturno
---

He revisado los specs auto-aprobados en modo nocturno.

1. Lista las features de `feature_list.json` con `"auto_approved": true`.
2. Si en los argumentos indico features concretas, actúa solo sobre esas;
   si no, sobre todas: $ARGUMENTS
3. Quita el campo `"auto_approved"` de cada una y añade una línea en
   `progress/history.md`: `- <fecha> — spec de <name> revisado por el humano.`
4. Si te pido cambios en algún spec, NO quites su marca: dime qué feature
   habría que reabrir y espera instrucciones.
