# Requirements — #68 bandeja_unificada_tomar_control

Spec compacto (modo rápido, sin harness). Cada R<n> se cubre con al menos un test.

- R1: La bandeja del panel de asesores lista todas las conversaciones de todos los canales, con o sin caso, y cada fila muestra su estado: `atendida_por_bot`, `atendida_por_asesor`, `pendiente` (escalada sin asesor) o `cerrada`.
- R2: Un asesor/supervisor puede abrir una conversación atendida por el bot y leerla (solo lectura, también en vivo); cada apertura se registra en auditoría (`conversation_read`).
- R3: Botón «Tomar conversación» (POST con CSRF): en UNA operación atómica crea el caso si no existe y lo asigna al asesor; desde ese momento el bot no responde. Si dos asesores toman a la vez, solo uno gana y el otro recibe un mensaje de «ya tomada».
- R4: «Devolver al bot» reutiliza el flujo actual de devolución y el bot retoma.
- R5: Las conversaciones atendidas por el bot son visibles a asesores y supervisores (ajuste `visibilidad_conversaciones_bot`, por defecto activo); los casos de supresión siguen restringidos como hoy.
- R6: El consentimiento previo (#35) no cambia: sin consentimiento no hay contenido guardado y no aparece en la bandeja.
- R7: Pruebas: estados, lectura + auditoría, tomar con y sin caso, concurrencia, devolver, permisos; `./init.sh` verde.
