# Prompts para Stitch (stitch.withgoogle.com)

Flujo: generar en Stitch → botón **Code** → pegar el HTML en este mismo directorio
como `dashboard.html` / `tabla.html`. Añadir screenshot PNG si se puede.
Luego Claude convierte eso en tokens CSS y re-skinnea `tvbot/api/static/dashboard.html`.

Modo recomendado en Stitch: **Experimental** (mejor con densidad de datos que Standard).
Target: **Web / Desktop**, no mobile.

---

## Prompt 1 — Pantalla principal (la que define TODO el sistema visual)

```
A professional dark-theme web dashboard for an algorithmic crypto & stocks
trading bot. Desktop layout, 1440px wide, dense but elegant — think Linear,
Vercel dashboard or a modern quant terminal. NOT a consumer fintech app,
no big illustrations, no rounded playful shapes.

Top bar: product name "tvbot" on the left with a small status pill
("PAPER · en vivo"), a two-option segmented switch (Crypto / TradFi),
and on the right a horizontal tab nav with 5 tabs:
Dashboard, Producción, Evaluación, Estrategias, Logs.

Body:
- A row of 5 compact KPI stat cards: Equity ($1,043.20), PnL Total (+$43.20),
  Trades cerrados (612), Win Rate (48.7%), Posiciones abiertas (7).
  Each card: small uppercase muted label, big bold number, small muted subtitle.
  Positive values in green, negative in red.
- A wide panel with a line chart titled "Curva de equity" (single line,
  subtle gradient fill, thin grid, no legend clutter).
- Below, two half-width panels side by side, each with a horizontal bar chart:
  "# Trades por estrategia" and "Rentabilidad por estrategia (USD)".
- A final panel "Posiciones abiertas ahora" with a dense data table:
  columns Estrategia, Símbolo, Lado, Entrada, Precio actual, PnL, Abierta hace.
  Lado shown as a small LONG/SHORT pill badge (green/red).

Style: dark near-black background, slightly lighter elevated cards with a
1px subtle border, blue as the single accent color, green/red only for
P&L semantics. Compact typography, tabular numerals for all figures.
Spanish labels.
```

## Prompt 2 — Pantalla de tabla densa + filtros (para Estrategias / Evaluación)

```
Same dark trading-bot dashboard, same design system as before. Now the
"Estrategias" screen.

Toolbar row: a search input ("Buscar estrategia..."), a 3-option segmented
control (Todas / ▲ Long / ▼ Short), and a checkbox "solo con trades".

Below: a wrapping row of ~20 selectable filter chips, each chip showing a
strategy code (e.g. "S31 ADX-short"), a tiny muted subtitle line, a small
LONG/SHORT tag, and a numeric count badge on the right. One chip is selected
(filled accent blue).

Then 4 compact KPI cards for the selected strategy, and a large panel
"Histórico de trades" with a dense scrollable table: Fecha, Símbolo, Lado,
Entrada, Salida, PnL, R múltiplo, Motivo de salida.
Include status badges in several colors: PASS (green), OK (blue),
RECOLECTANDO (grey), VIGILAR (amber), FAIL (red).

Show clearly how empty states, hover rows and sticky table headers look.
```

## Prompt 3 (opcional) — Logs

```
Same dark dashboard design system. "Logs" screen: a panel with two
datetime pickers, a "Ver" secondary button and a "⬇ Descargar rango"
primary button; below, a monospace log viewer block with scroll and
color-coded severity lines. Then a panel "Eventos recientes" with a
compact timeline list.
```

---

## Qué necesito de vuelta (mínimo viable)

1. `design/stitch/dashboard.html`  ← el "Code" del prompt 1
2. `design/stitch/tabla.html`      ← el "Code" del prompt 2 (opcional pero muy útil)
3. Screenshots PNG de ambos (opcional)

Con solo el #1 ya puedo re-skinnear las 5 tabs de forma coherente.
