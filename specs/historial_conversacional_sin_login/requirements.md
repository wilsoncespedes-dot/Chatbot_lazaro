# Requirements — historial_conversacional_sin_login

Servicio: `orchestrator` (`services/orchestrator/`). La feature reutiliza el
historial de mensajes del contacto que ya guarda el servicio.

## R1
CUANDO una conversación está en estado `ACTIVE`, `MEMORY_ENABLED=true`,
`IDENTITY_LOGIN_REQUIRED=false` y no existe sesión autenticada de cliente, el
fallback conversacional DEBE incluir los mensajes recientes previos del mismo
contacto.

## R2
CUANDO se construye el historial para el fallback conversacional, el sistema
DEBE excluir el mensaje actual que ya se persistió antes de ejecutar el LLM.

## R3
CUANDO se construye el historial para el fallback conversacional, el sistema
DEBE limitar el número de mensajes a `MEMORY_CONTEXT_MESSAGES`.

## R4
CUANDO se construye el historial sin sesión autenticada, el sistema DEBE
mantener aislados los mensajes por contacto y canal usando el repositorio
existente.

## R5
SI `MEMORY_ENABLED=false` ENTONCES el sistema NO DEBE incluir mensajes previos
ni memoria permanente en el prompt conversacional.

## R6
SI el flujo de consentimiento configurado no ha sido aceptado ENTONCES el
orquestador NO DEBE enviar mensajes previos del contacto al LLM.

## R7
CUANDO existe una sesión autenticada activa, el fallback conversacional DEBE
conservar el contexto de historial y memoria permanente existente.

## R8
El modo conversacional DEBE reutilizar la tabla de mensajes y el repositorio
actuales, sin añadir tablas ni servicios.

## R9
SI `IDENTITY_LOGIN_REQUIRED=true` ENTONCES el orquestador DEBE conservar el
flujo actual de login y NO DEBE permitir que el modo conversacional lo evada.

