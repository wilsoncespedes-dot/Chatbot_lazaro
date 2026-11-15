# Requirements — rediseño_visual_paneles (#56)

Servicio: **orchestrator** (único afectado). Alcance: hoja de estilos compartida
`ADMIN_CSS` (`GET /admin/static/admin.css`) y las plantillas HTML de
`admin.py`, `advisor_panel.py`, `two_factor_page.py` e `identity_page.py`.
Fuera de alcance: lógica de negocio, rutas, formularios, permisos, JS y
dependencias.

## Identidad visual compartida (acceptance 1)

## R1
El sistema DEBE definir en `ADMIN_CSS` un conjunto de variables CSS (`:root`) de
color, espaciado, radio, sombra y tipografía que ambos paneles (admin y asesor)
consumen desde la misma hoja `/admin/static/admin.css`.

## R2
El sistema DEBE definir en `ADMIN_CSS` una escala tipográfica con estilos
distintos para `h1` (cabecera), `h2` (título de página) y `h3` (sección).

## R3
El sistema DEBE renderizar la cabecera y la navegación de `admin.render_page` y
de `advisor_panel._page` con las mismas clases CSS compartidas (`site-header`,
`site-nav`), de modo que ambos paneles tengan idéntica estructura visual.

## R4
El sistema DEBE definir en `ADMIN_CSS` estilos diferenciados para los botones
primario (por defecto), secundario y de acción destructiva, y aplicarlos solo
mediante clases añadidas al HTML existente.

## R5
El sistema DEBE definir en `ADMIN_CSS` estilos de tarjeta de sección (`.card`)
y de insignia de estado (`.badge`) con variantes semánticas (`ok`, `warn`,
`error`, `info`).

## Adaptación a móvil y escritorio (acceptance 2)

## R6
El sistema DEBE incluir en cada página de ambos paneles
`<meta name="viewport" content="width=device-width, initial-scale=1">`.

## R7
MIENTRAS el ancho de la ventana es 375 px, el sistema DEBE declarar en
`ADMIN_CSS` una consulta `@media (max-width: …)` que apile la navegación y los
formularios en una columna y haga que controles y botones ocupen el ancho
disponible.

## R8
El sistema DEBE declarar en `ADMIN_CSS` que toda `table` queda contenida en un
contenedor con desplazamiento propio (`overflow-x: auto; max-width: 100%`), de
modo que el documento no produzca desplazamiento horizontal a 375 px ni a
1280 px.

## R9
MIENTRAS el ancho de la ventana es 1280 px, el sistema DEBE limitar el ancho de
`main` a un máximo declarado y centrarlo, de modo que la bandeja de casos use un
máximo mayor que el de las páginas de formularios.

## R10
El sistema DEBE conservar en el HTML de cada página, tras el rediseño, todos los
formularios, botones, enlaces y campos que existían antes (sin pérdida de
acciones en móvil).

## Accesibilidad y estados (acceptance 3)

## R11
El sistema DEBE definir en `ADMIN_CSS` un indicador de foco visible
(`:focus-visible` con `outline` de al menos 2 px) para `a`, `button`, `input`,
`select` y `textarea`, sin usar `outline: none` sin sustituto.

## R12
El sistema DEBE definir en `ADMIN_CSS` estados `:hover` y `:disabled` para
botones y enlaces de navegación, y un estado visible de enlace activo
(`aria-current="page"`).

## R13
El sistema DEBE elegir las parejas de color texto/fondo de `ADMIN_CSS` con una
relación de contraste mínima de 4.5:1 para texto normal y 3:1 para bordes de
controles, y un test DEBE calcular dichas relaciones a partir de las variables
declaradas.

## R14
El sistema DEBE definir en `ADMIN_CSS` estilos distintos para `.error`
(`role="alert"`), `.ok` (`role="status"`) y campos inválidos
(`:user-invalid` / `[aria-invalid="true"]`), que no dependan solo del color
(borde lateral y/o prefijo textual).

## R15
El sistema DEBE añadir a cada página un enlace «Saltar al contenido»
(`href="#contenido"`) como primer elemento enfocable del `body`, y
`id="contenido"` en `main`.

## R16
El sistema DEBE marcar la navegación con `<nav aria-label="…">` y el enlace de
la sección actual con `aria-current="page"` en `admin.render_page` y en
`advisor_panel._page`.

## R17
DONDE el usuario declara `prefers-reduced-motion: reduce`, el sistema DEBE
anular transiciones y animaciones en `ADMIN_CSS`.

## Estados de casos y tablas (acceptance 3)

## R18
El sistema DEBE renderizar el estado del caso en la bandeja y en la vista de
caso (`advisor_panel`) como `<span class="badge …">` con el mismo texto que
antes, con clase semántica distinta para abierto, asignado y cerrado.

## R19
El sistema DEBE definir en `ADMIN_CSS` estilos de tabla con cabecera
diferenciada, filas alternas, `:hover` de fila y relleno suficiente para ser
legible.

## Preservación de comportamiento (acceptance 4)

## R20
El sistema NO DEBE modificar rutas, métodos HTTP, atributos `action`/`method`,
nombres de campos, tokens CSRF, comprobaciones de rol ni la lógica de
`admin_routes.py` y `advisor_routes.py`.

## R21
El sistema DEBE seguir emitiendo en `GET /admin/static/admin.css` las cabeceras
de `admin.security_headers()` y en las páginas del panel de asesores
`admin.panel_security_headers()` sin cambios en `CSP` ni `PANEL_CSP`.

## R22
El sistema DEBE conservar el texto visible, el escapado HTML y los atributos
`role`, `data-error` y los identificadores usados por `panel_live.js`
(regiones en vivo) en cada página afectada.

## Restricciones técnicas y CSP (acceptance 5)

## R23
El sistema NO DEBE emitir atributos `style=`, elementos `<style>`, `<script>`
nuevos, hojas o fuentes externas (`http://`, `https://`, `//`), `@import` ni
`url(` con origen externo en las páginas ni en `ADMIN_CSS`.

## R24
El sistema NO DEBE añadir dependencias a `requirements*.txt`, `pyproject.toml`
ni archivos estáticos nuevos; todo estilo reside en `ADMIN_CSS`.

## R25
CUANDO un navegador pide una página de cualquier panel, el sistema DEBE
mantener `script-src 'self'` y `default-src 'self'` en la CSP, de modo que la
hoja `/admin/static/admin.css` y `panel_live.js` se carguen bajo esas políticas.

## Pruebas (acceptance 6)

## R26
El sistema DEBE incluir pruebas automáticas que verifiquen R1–R25 sobre
`ADMIN_CSS` y sobre el HTML renderizado de las páginas principales de admin
(inicio, perfiles, manuales, ajustes, métricas, login, 2FA) y de asesor
(login, inicio, bandeja, caso, supresiones, métricas, error).

## R27
CUANDO se ejecuta `./init.sh`, el sistema DEBE terminar con código 0 y la suite
completa del orchestrator DEBE pasar.
