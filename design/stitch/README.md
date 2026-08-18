# Stitch → tvbot: pipeline de rediseño

## Estado

| Recurso | Valor |
|---|---|
| Proyecto Stitch | `projects/4002007751741312022` |
| Design system | `assets/5598524333401558227` — "tvbot terminal dark" |
| MCP registrado | `claude mcp add stitch --transport http https://stitch.googleapis.com/mcp --header "X-Goog-Api-Key: …" -s user` |
| Driver | `scratchpad/stitch.py` + `scratchpad/gen_screens.py` |

## Por qué hay un driver en vez de usar el MCP directo

El servidor conecta bien, pero Claude Code no puede cargar su `tools/list`:

```
stitch: https://stitch.googleapis.com/mcp (HTTP) - ! Connected ·
  tools fetch failed — can't resolve reference #/$defs/ScreenInstance from id #
```

Es un `$ref` sin resolver en el schema que publica Google (afecta a
`create_design_system_from_design_md` y `apply_design_system`). Hasta que lo
arreglen, se habla con el server por JSON-RPC sobre HTTP con `stitch.py`, que
expone exactamente las mismas tools. Cuando Google lo corrija, el MCP ya está
registrado y las tools aparecen solas.

## Herramientas disponibles

`create_project` · `get_project` · `delete_project` · `list_projects` ·
`list_screens` · `get_screen` · `generate_screen_from_text` · `edit_screens` ·
`generate_variants` · `upload_design_md` · `create_design_system` ·
`create_design_system_from_design_md` · `update_design_system` ·
`list_design_systems` · `apply_design_system`

Modelos: `GEMINI_3_1_PRO` (el usado) o `GEMINI_3_FLASH`.

## Cómo se le pasó el diseño base

No existe una tool que acepte HTML o screenshot como entrada. La forma de que
Stitch respete tu diseño actual es el campo `theme.designMd` del design system:
un markdown con tus tokens exactos extraídos de `tvbot/api/static/dashboard.html`
(`#0d1117`, `#161b22`, `#30363d`, `#1f6feb`, `#3fb950`, `#f85149`, `#d29922`,
radios 8/10px, paddings, escala tipográfica) + el inventario de componentes
reales + una lista explícita de qué mejorar y qué está prohibido.

Ese design system se pasa como `designSystem` en cada `generate_screen_from_text`,
así las 5 pantallas salen consistentes entre sí y ancladas a tu identidad.

## Integración con el proyecto

Las pantallas de Stitch son **mockups estáticos con datos inventados**. No se
copian al proyecto. Lo que se extrae y se integra:

1. **Capa de tokens** → reescribir el bloque `:root` y el `<style>` de
   `dashboard.html` con los valores refinados (espaciado, escala tipográfica,
   `font-variant-numeric: tabular-nums`, estados hover/focus, elevaciones).
2. **Componentes** → re-skin de `.card`, `.panel`, `table`, `.badge.*`, `.chip`,
   `.seg`, `.btn`, `.note-banner`, `pre`. Mismos nombres de clase → cero cambios
   en el JS que las genera.
3. **Markup quirúrgico** → solo donde el diseño lo exija (agrupar columnas,
   cabecera pegajosa, primera columna congelada, estados vacíos). **Se preservan
   todos los `id` y `onclick`**: `page-dash`, `t-open`, `t-hist`, `t-eval`,
   `t-events`, `strat-chips`, `ch-equity`, `ch-ntrades`, `ch-pnl`, `show()`,
   `setMarket()`, `setFilter()`, `renderChips()`, `viewLogs()`, `downloadLogs()`.
4. **Chart.js** → los colores están hardcodeados en JS
   (`dashboard.html:308-326`: `#58a6ff`, `#3fb950`, `#f85149`, `#8b949e`,
   `#21262d`). Hay que leerlos de las CSS vars con `getComputedStyle` para que
   los charts sigan al tema en vez de divergir.

### Verificación

`git diff` debe mostrar cambios solo en `<style>` y en markup de presentación.
Después: levantar la API y comprobar que las 5 tabs cargan, los 3 charts pintan,
los filtros de Estrategias responden y el visor de logs descarga.

## Repetir / iterar

```bash
export STITCH_API_KEY="…"
python scratchpad/stitch.py edit_screens '{"projectId":"4002007751741312022",
  "selectedScreenIds":["<id>"],"prompt":"más densa la tabla, menos padding vertical",
  "modelId":"GEMINI_3_1_PRO","deviceType":"DESKTOP"}'
```

Para cambiar la identidad global: `update_design_system` sobre
`assets/5598524333401558227` y luego `apply_design_system` a las 5 pantallas.
