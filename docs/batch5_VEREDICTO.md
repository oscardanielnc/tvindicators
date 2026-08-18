# Veredicto — Batch 5: momentum-systems (Ichimoku, KST, TSI, Awesome Oscillator)

**Fecha:** 2026-06-15 · store 52 monedas 1h · costos+funding · motor de continuación · gate DURO (IS>0 Y OOS>0).

## TL;DR — redundantes en monedas cubiertas, valiosos en monedas NUEVAS
78 setups pasan el gate duro — demasiados, porque AO/KST/TSI/Ichimoku son variaciones de momentum
y en su mayoría **re-detectan el mismo edge** que el roster (ADX/Vortex/Squeeze/B-Xtrender). PERO al
aplicarlos a **monedas que el roster NO cubre** aparece diversificación genuina.

## Validación (6 candidatos de moneda nueva)
| Candidato | n | exp/PF | IS / OOS | corr roster |
|-----------|---|--------|----------|-------------|
| NEAR-AO-S | 83 | 116/1.80 | 126 / 101 | 0.03 |
| TAO-AO-S | 73 | 103/1.45 | 88 / 109 | 0.04 |
| LINK-KST-L | 122 | 89/1.54 | 86 / 92 | 0.24 |
| NEO-AO-L | 46 | 78/1.53 | 55 / 122 | 0.04 |
| ICP-KST-S | 247 | 74/1.46 | 41 / 119 | 0.07 |
| ALGO-TSI-S | 118 | 77/1.54 | 79 / 73 | 0.04 |

**corr mutua media 0.03 · 5.8/6 apuestas efectivas** → independientes entre sí y del roster. IS>0 y OOS>0
en los 6. 2 longs (LINK, NEO) ayudan al balance long/short.

## Promovidas ✅ (S39-S44, role 0.5)
S39 LINK-L (KST), S40 NEO-L (AO), S41 ICP-S (KST), S42 NEAR-S (AO), S43 ALGO-S (TSI), S44 TAO-S (AO).
KST/AO/TSI añadidos a `tvbot/indicators.py` (paridad exacta). `--once` corre las 44; tests OK.

## Lección reusable
Los osciladores de momentum (AO/KST/TSI/Ichimoku) NO aportan edge nuevo sobre monedas ya cubiertas por
el roster trend/momentum (redundantes). Su valor está en **expandir el universo a monedas nuevas**. La
diversificación real vino de aplicar señales conocidas a coins no cubiertas, no del indicador en sí.

## Artefactos
`poc_batch5.py` (sweep + gate duro IS>0&OOS>0) · `valida_batch5.py` (corr vs roster + corr mutua).
Ver [[batch4-volumen-redundante]] (misma lección de redundancia) y [[batch3-adx-squeezeshort]] (edge ortogonal real).
