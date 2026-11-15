# Design — rediseño_visual_paneles (#56)

## Archivos a tocar

Solo en `services/orchestrator/`:

- `orchestrator/admin.py`: reescribe `ADMIN_CSS`; ajusta `render_page` (skip
  link, `header.site-header`, `nav.site-nav` con `aria-label`, `id="contenido"`,
  `aria-current`); añade clases a botones/mensajes existentes.
- `orchestrator/advisor_panel.py`: ajusta `_page` igual que `render_page`;
  `<span class="badge …">` para el estado de caso en `render_inbox_table` y
  `render_advisor_case`; clases `.card`/`.btn-*` en secciones y formularios.
- `orchestrator/two_factor_page.py`, `identity_page.py`: heredan `_page`; solo
  ajustar clases si hace falta (la hoja y la cabecera ya son compartidas).
- Tests nuevos: `tests/test_panel_visual.py`. Tests existentes que comparen
  HTML literal (`test_admin*.py`, `test_advisor_panel.py`) se ajustan solo si
  rompen por clases añadidas, sin cambiar sus aserciones de comportamiento.

No se tocan `admin_routes.py`, `advisor_routes.py`, `contracts/`, otros
servicios, `.env.example`, ni `panel_live.js` (salvo lectura para conservar sus
selectores, R22).

## Firmas nuevas

Ninguna función pública nueva. Helpers privados opcionales en `admin.py`:

```python
def _nav_html(links: list[tuple[str, str]], current: str | None, label: str) -> str: ...
def _skip_link() -> str: ...
```

`advisor_panel._page` reutiliza `admin._nav_html`/`admin._skip_link` para
garantizar R3. `current` se deduce con un parámetro opcional `current_path:
str | None = None` en `render_page`/`_page` (por defecto `None`: sin
`aria-current`), así no cambian los llamadores existentes; los renders
principales lo pasan por prefijo de ruta.

## Diseño del CSS

- Variables en `:root`: `--bg`, `--surface`, `--text`, `--muted`, `--primary`,
  `--primary-contrast`, `--border`, `--ok`, `--warn`, `--danger` (+ fondos
  suaves), `--radius`, `--space-1..4`, `--shadow`, `--font`.
- Fuente: pila del sistema (`system-ui, -apple-system, "Segoe UI", sans-serif`);
  sin fuentes remotas.
- Móvil primero: layout base de una columna; `@media (min-width: 48rem)`
  restaura filas flex de formularios y navegación horizontal. `main` máx.
  `72rem` en bandeja (`main:has(.inbox)` no se usa por compatibilidad; en su
  lugar `main { max-width: 64rem }` y `.wide` se añade a `main` solo en la
  bandeja mediante parámetro `wide: bool = False` en `_page`).
- Tablas: `table { display: block; overflow-x: auto; max-width: 100% }` con
  `thead/tbody` como `display: table` interno no es fiable; se usa en su lugar
  un `<div class="table-wrap">` generado por los renders (envuelve
  `<table>` sin cambiar su contenido). Los tests que buscan `<table` siguen
  pasando.
- Foco: `:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px }`.
- Contraste: texto `#1b2733` sobre `#ffffff`/`#f4f6fa` (>12:1); primario
  `#1d4ed8` con texto blanco (≈6.7:1); `.error` texto `#8a1c1c` sobre `#fdecec`
  (≈7:1); `.ok` `#14532d` sobre `#e6f4ea`; bordes de control `#6b7a8d` sobre
  blanco (≥3:1).
- No se usa `style=`, `@import`, `url()` ni imágenes: iconografía solo con
  texto/CSS (`::before` con caracteres).
- El estado no depende solo del color: `.error::before` y `.badge` incluyen
  texto; borde lateral grueso en alertas.

## Excepciones

Ninguna nueva. No cambia el manejo de `DomainError`/`HTTPException`.

## Alternativa descartada

Tablas apiladas tipo tarjeta en móvil con `data-label` por celda: obliga a
modificar cada fila de ~12 tablas y a duplicar texto, con riesgo para los
fragmentos en vivo (`/asesor/live/*`) y los tests de HTML. Se descartó a favor
de un contenedor `.table-wrap` con desplazamiento interno, que mantiene todas
las columnas y acciones sin tocar el marcado de las celdas. También se descartó
añadir un framework CSS (Pico/Bootstrap) por la restricción de CDN/dependencias.

## Dependencias nuevas

Ninguna. Sin reutilización de código externo (sin licencia que confirmar).

## Supuestos a confirmar

- Sin cambios en `docs/proyecto.md` §12. Paleta, tipografía y breakpoint
  (`48rem`) son defaults de diseño, editables en `ADMIN_CSS` sin configuración
  de entorno. No se añaden variables a `.env.example`.
- `<div class="table-wrap">` en los fragmentos en vivo: el cliente reemplaza la
  región completa, por lo que no duplica filas (R22); el test existente de
  fragmentos debe seguir verde.

## Estrategia de pruebas

`tests/test_panel_visual.py` (sin navegador):

- Parseo de `ADMIN_CSS`: variables, media queries, `:focus-visible`,
  `prefers-reduced-motion`, ausencia de `url(`/`@import`/`http` (R1, R2, R4,
  R5, R7, R8, R11, R12, R14, R17, R19, R23).
- Contraste WCAG calculado desde variables (R13).
- Render de páginas admin y asesor con `TestClient`/funciones `render_*`:
  skip link, `id="contenido"`, `aria-label`, `aria-current`, viewport, sin
  `style=`/`<style>`/scripts externos, formularios/CSRF/acciones preservados
  (R3, R6, R10, R15, R16, R18, R20, R22, R23).
- Cabeceras CSP/`nosniff`/`no-store` en CSS y páginas (R21, R25).
- Diff de dependencias: `git diff` sin cambios en requirements (R24; revisado
  por reviewer, test comprueba que no hay archivos estáticos nuevos).
- R27: `./init.sh`.
