---
name: "source-command-estado"
description: "Ejecuta init.sh y resume el estado del arnés y de las features"
---

# source-command-estado

Use this skill when the user asks to run the migrated source command `estado`.

## Command Template

Ejecuta `./init.sh`. Con su resultado, `feature_list.json` y `progress/current.md`, dame un
resumen breve: si el entorno está verde, qué feature está en curso (si
hay) y cuál es el siguiente paso según el flujo SDD. Si hay features con
`"auto_approved": true`, features `blocked` o informes
`progress/nocturno_*.md` recientes, menciónalos: son lo que el humano debe
revisar al volver. No lances subagentes.
