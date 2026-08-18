# Veredicto — Batch 2: Reversión a la media (Connors RSI2 + Bollinger %b)

**Fecha:** 2026-06-15 · **Datos:** store completo 52 monedas 1h (~2022→2026-06) · costos + funding reales · IS<2025 / OOS≥2025
**Motor nuevo:** `run_mr` — entra en extremo (sobreventa/sobrecompra en tendencia), sale al volver a la media (SMA corta), SL 3×ATR, timeout 24h. Distinto al motor de continuación del roster.

## TL;DR — funciona, pero es marginal y NO encaja la filosofía
La reversión a la media **sí tiene edge real y OOS-robusto** en un puñado de monedas, pero con un perfil **opuesto al roster**: alta frecuencia, **win-rate alto (65-73%)** y **edge fino (19-54 bps/trade)** — 3 a 10× menor por trade que SQZ/VTX (55-248 bps). Es la inversa del roster (32-47% WR, ganadores que corren). Útil como diversificador por su distribución distinta, pero **arriesgado en vivo** porque el edge fino está más cerca de la línea de costos (justo lo que mató al proyecto `btc`).

## Sweep (52 monedas × 2 lados × 6 combos)
18 setups pasan full+OOS (exp>0, PF≥1.4, n≥40, años+ Y OOS exp>0, n≥12). Pero muchos con **OOS_PF marginal (1.02-1.22)** = probable ruido. Robustez (sensibilidad a umbral/exit + corr vs roster) sobre los 5 mejores:

| Candidato | exp full | OOS exp | sens umbral | sens exit | corr roster | veredicto |
|-----------|----------|---------|-------------|-----------|-------------|-----------|
| **INJ BB%b-L** | 54 | 24 | [36,54] | [39,54] | 0.01 | ✅ ROBUSTO (el mejor, moneda nueva) |
| **ARB CRSI-S** | 29 | 29 | [4,29] | [29,36] | −0.07 | ✅ ROBUSTO (IS=OOS) |
| **XLM CRSI-L** | 25 | 37 | [10,34] | [10,25] | 0.08 | ✅ ROBUSTO |
| **EGLD CRSI-L** | 37 | 20 | [2,37] | [25,37] | 0.02 | ✅ robusto (umbral roza 0) |
| OP CRSI-S | 26 | 34 | [−1,29] | [11,29] | −0.02 | ❌ FRÁGIL (umbral negativo) |

Los 4 robustos son **descorrelacionados del roster (corr ~0)** → diversifican de verdad.

## Caveats (honestos)
1. **Edge fino = riesgo de costos en vivo.** 24-54 bps NETOS (ya con 13 bps de costo + funding). El slippage real en las salidas por SL (taker, alta frecuencia) puede comerse más que en batch 1. Es el modo de falla exacto del proyecto `btc` (MR-ish thin edge + costos).
2. **Mismatch de filosofía.** El proyecto premia "raras y buenas" (baja frecuencia, ganancia asimétrica). Esto es frecuente y de ganancia chica. WR alto NO es el edge — la asimetría sí, y aquí es al revés (losers ~2-3× winners, salvados por WR 70%).
3. **Solapes de moneda intra-roster:** ARB ya tiene S26 (ARB-VTX-S) y XLM tiene S14 (XLM-L) — antes de promover ARB-CRSI-S / XLM-CRSI-L hay que medir corr DIRECTA con esas (no solo vs roster agregado). INJ es moneda nueva (limpia).

## PROMOVIDO (parcial, 2026-06-15) ✅
Se promovió **solo INJ BB%b-L como S30** (role 0.5, peso bajo) — el representante más limpio de la clase
reversión (moneda nueva sin solape, edge más alto 54 bps, robusto, corr 0.01). Requirió un motor de
salida nuevo en el bot: **`exit_mode='meanrev'`** (salida al recuperar la SMA20 + SL 3×ATR + timeout 24h).
Paridad exacta verificada (n=232, exp 54 bps, PF 1.50); `python -m tvbot --once` corre las 30 OK; tests de
salidas OK. Los demás (ARB-S, XLM-L, EGLD-L) quedan documentados, no promovidos.

## Recomendación (original)
**NO promover el batch 2 en bloque.** A diferencia de batch 1 (fat-edge, encaja filosofía), esto es secundario.
- Si se quiere un representante de la clase "reversión" para el dataset de paper trading (la meta es producir candidatos a evaluar): el más limpio es **INJ BB%b-L** (moneda nueva, edge más alto, robusto, corr 0.01), opcionalmente + **ARB-CRSI-S**. Como sleeve aparte, peso bajo, claramente etiquetado.
- Prioridad mayor: **batch 3 = buscar más indicadores de edge GRUESO y baja frecuencia** (estilo SQZ/VTX), que es donde está la filosofía y el margen sobre costos. Candidatos no probados: Fisher Transform, KAMA-cross, Vortex en longs, Squeeze en shorts, ADX/Choppiness como filtro de régimen para subir el edge de los existentes.

## Artefactos
`poc_meanrev.py` (sweep + OOS integrado, motor run_mr) · `valida_meanrev.py` (sensibilidad + corr).
**Lección reusable:** la reversión a la media en cripto perp 1h existe pero es de edge fino; el motor de salida importa tanto como la entrada. No confundir WR alto con edge (ver también la lección de [[youtube-1m-sd-confluence-replica]]).
