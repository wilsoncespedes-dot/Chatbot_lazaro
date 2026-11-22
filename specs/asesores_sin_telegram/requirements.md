# Requirements — asesores_sin_telegram (#65)

Servicio: `orchestrator` (panel de asesores y Perfiles y roles). Pedido del
usuario: los asesores no deben necesitar Telegram vinculado y el panel ya no
debe generar el enlace de vinculación.

## R1
CUANDO un asesor o supervisor sin Telegram vinculado abre `/asesor`, el
sistema DEBE mostrar el Inicio completo (accesos, presencia y acciones) sin
aviso de vinculación.

## R2
El panel de asesores NO DEBE rechazar ninguna vista ni acción por falta de
Telegram vinculado y NO DEBE conservar el error `telegram_not_linked`.

## R3
La página Perfiles y roles NO DEBE mostrar el botón "Generar enlace" ni las
columnas "Telegram vinculado" y "Enlace de Telegram".

## R4
`POST /admin/profiles/{id}/link-token` NO DEBE existir y NO DEBE emitirse
ningún token de vínculo desde el panel.
