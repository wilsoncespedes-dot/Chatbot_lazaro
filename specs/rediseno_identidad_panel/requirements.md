# Requirements — rediseno_identidad_panel (#60)

Servicio: `orchestrator` (panel administrativo `/admin`, panel de asesores
`/asesor` y página pública `/acceso`). Sustituye la identidad visual de #56
por la nueva identidad (turquesa/verde azulado, tarjetas redondeadas, menú
lateral agrupado) tomada del prototipo del dueño. El nombre visible sigue
siendo **Lázaro Software**. No cambia rutas, formularios, campos, CSRF ni
cabeceras de seguridad.

## Identidad visual

## R1
El sistema DEBE declarar en el primer bloque `:root` de `ADMIN_CSS` los tokens
de la nueva identidad: `--brand` `#0f5257`, `--accent` `#1fc5d6`,
`--btn` `#0b7f8a`, `--bg` `#eef8f8` y `--line` para divisores decorativos.

## R2
El sistema DEBE redefinir los tokens de color para modo oscuro dentro de
`@media (prefers-color-scheme: dark)`.

## R3
El sistema DEBE mantener contraste WCAG de 4.5:1 en los pares de texto
(`--text`/`--surface`, `--text`/`--bg`, `--primary`/`--primary-contrast`,
estados ok/warn/danger/info) y 3:1 en `--border` sobre `--surface` y `--bg`.

## Estructura compartida

## R4
MIENTRAS haya sesión, cada página de `/admin` y `/asesor` DEBE renderizarse
dentro de un contenedor `.shell` con una barra lateral `aside.sidebar` que
muestre la marca "Lázaro Software".

## R5
MIENTRAS haya sesión, la barra superior `header.site-header` DEBE mostrar la
ruta `Panel / <título de la página>`.

## R6
MIENTRAS haya sesión en `/admin`, la navegación DEBE agrupar los enlaces en
"Operación" (Inicio, Eventos recientes, Clientes, Métricas), "Contenido"
(Manuales, Plantillas, Respuestas guardadas, Textos del flujo),
"Organización" (Categorías, Etiquetas) y "Administración" (Perfiles y roles,
Ajustes, Supresiones), en ese orden.

## R7
Cada enlace de la navegación lateral DEBE llevar un icono SVG en línea con
`aria-hidden="true"`.

## R8
MIENTRAS haya sesión, la barra lateral DEBE terminar con el formulario de
salida (`/admin/logout` o `/asesor/logout`) con su campo CSRF.

## R9
El título de cada página con sesión DEBE renderizarse como `<h1>` dentro de
`main#contenido`.

## R10
El sistema DEBE conservar el enlace de salto como primer elemento del
`<body>`, la navegación con `aria-label` y `aria-current="page"` en el enlace
activo.

## Inicio

## R11
CUANDO un administrador abre `/admin`, el sistema DEBE mostrar accesos
rápidos como tarjetas enlazadas a Clientes, Manuales, Plantillas, Etiquetas,
Textos del flujo y Métricas.

## Textos del flujo

## R12
CUANDO un administrador abre `/admin/texts`, el sistema DEBE mostrar un
editor de dos columnas: a la izquierda la lista de mensajes agrupada en
"Consentimiento legal", "Conversación", "Sesión y acceso" y
"Servicio y casos"; a la derecha el mensaje seleccionado.

## R13
El editor de textos DEBE seguir enviando todos los campos de
`TEXT_FIELD_LABELS` en un único formulario `POST /admin/texts` con CSRF.

## R14
Cada mensaje del editor DEBE mostrar su grupo, su nombre, su versión vigente
y el enlace a su historial.

## R15
El aviso de reaceptación legal DEBE mostrarse solo en los mensajes
`notice_text` y `notice_version`.

## R16
SI un campo de `TEXT_FIELD_LABELS` no pertenece a ningún grupo ENTONCES el
sistema DEBE mostrarlo en un grupo "Otros" para no perderlo.

## R17
MIENTRAS no haya fragmento en la URL, el editor DEBE mostrar el primer
mensaje y marcarlo como actual; la selección DEBE funcionar sin JavaScript.

## Perfiles y roles

## R18
CUANDO un administrador abre `/admin/profiles`, el sistema DEBE mostrar el
formulario "Nuevo perfil" en una tarjeta y la tabla con avatar de inicial,
rol como insignia y "Telegram vinculado" como Sí/No con indicador.

## Inicio de sesión

## R19
Las páginas de inicio de sesión de `/admin/login`, `/asesor/login` y
`/acceso` DEBEN renderizarse con el diseño de acceso: fondo con curvas SVG
decorativas en línea, título del panel y tarjeta translúcida "Iniciar sesión".

## R20
Los campos Usuario y Contraseña del inicio de sesión DEBEN mostrar un icono
decorativo y conservar `name`, `autocomplete` y `required`.

## Seguridad y adaptación

## R21
Las páginas y `ADMIN_CSS` NO DEBEN incluir `style=`, `<style`, `@import`,
`url(` ni recursos externos, y NO DEBEN añadirse archivos estáticos.

## R22
A 48rem o menos, la barra lateral DEBE pasar a la parte superior con la
navegación desplazable en horizontal y los formularios DEBEN ocupar el ancho.

## Panel de asesores

## R23
MIENTRAS haya sesión en `/asesor`, la navegación DEBE agruparse según el rol:
"Atención" (Inicio, Casos) salvo para `responsable_datos`, "Supervisión"
(Todos los casos, Métricas) solo para `supervisor`, y "Privacidad"
(Supresiones).

## R24
CUANDO un asesor o supervisor abre `/asesor`, el sistema DEBE mostrar accesos
rápidos (Bandeja de casos; además Todos los casos y Métricas para
`supervisor`), la tarjeta "Mi presencia" con su estado y las acciones
Responder, Asignarme y Cerrar como tarjetas, conservando acciones, campos y
CSRF.

## R25
Las páginas de métricas de `/admin/metricas` y `/asesor/metricas` DEBEN
mostrar las cifras de primera respuesta como tarjetas y las tablas por asesor
y por motivo con encabezados, sin formularios en la vista del supervisor.

## R26
Los inicios de sesión de `/admin/login`, `/asesor/login` y `/acceso` DEBEN
ofrecer junto a la contraseña un botón discreto (icono de ojo) que alterne
entre mostrarla y ocultarla, cargado desde `/admin/static/login.js` y oculto
cuando no hay JavaScript.
