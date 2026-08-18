# Veredicto — Batch 4: Volumen/flujo (OBV, CMF, Force Index) + Schaff Trend Cycle

**Fecha:** 2026-06-15 · store 52 monedas 1h · costos+funding · IS<2025/OOS≥2025 · motor de continuación.

## TL;DR — descubrimiento (mayormente) NEGATIVO, pero útil
Probé la dimensión que el roster casi no usa: **volumen** (OBV, Chaikin Money Flow, Force Index) +
Schaff Trend Cycle. El sweep dio 44 setups full+OOS, pero **dos problemas al mirar de cerca**:
1. Muchos tienen **IS negativo / OOS positivo** (regime-luck en 2025-26, no edge estable).
2. Los robustos son casi todos **shorts de alts que YA están en el roster**, y la corr directa lo confirma:
   **0.62-0.73 vs el Vortex/ADX short del mismo par** → el volumen RE-DETECTA el mismo down-move.
   No diversifica. Promoverlos sería inflar el conteo de estrategias sin añadir apuestas reales.

**Lección reusable:** sobre cripto perp 1h, el volumen (OBV/CMF/FI) en SHORT de alts es en gran parte
una relectura del momentum-trend que ADX/Vortex ya capturan. No vale la pena seguir minando ese cruce.

## Lo que SÍ aporta (no redundante, estable IS+OOS+sensibilidad)
| Candidato | IS / OOS exp | PF full | corr vs roster | Por qué aporta |
|-----------|--------------|---------|----------------|----------------|
| **ORDI-CMF-L** | 152 / 150 | 1.46 | par NUEVO | moneda nueva + **long** (roster es short-heavy), IS≈OOS |
| **ORDI-FI-L** | 43 / 171 | 1.47 | par NUEVO | moneda nueva + **long**; corr 0.09 con ORDI-CMF-L (distinta) |
| **EGLD-FI-S** | 48 / 127 | 1.49 | 0.40 vs S18/S32 | short pero solo 0.40 corr con los shorts EGLD existentes |

Redundantes descartados (corr>0.5): RUNE-FI-S (0.73 vs S27), SEI-FI-S (0.72 vs S25), SEI-STC-S (0.64),
ARB-FI-S (0.62 vs S26). Inestables (IS<0): ORDI-STC-L, WIF-FI/CMF/OBV-S, ADA-CMF-S, etc.

## Recomendación
Promover los **2 ORDI longs (CMF-L, FI-L)** — son la mejor parte: moneda nueva, lado long que falta, y
mutuamente descorrelacionados. **EGLD-FI-S opcional** (corr 0.40, aporte modesto). NO promover los
volume-shorts redundantes. Valor del batch: bajo en cantidad, pero el descubrimiento negativo evita
trabajo futuro inútil y los 2 ORDI longs ayudan al balance long/short.

Requiere replicar OBV/CMF/Force Index en `tvbot/indicators.py` (STC no hace falta: ningún promovido lo usa).

## Artefactos
`poc_batch4.py` (sweep OBV/CMF/FI/STC + OOS) · `valida_batch4.py` (sensibilidad + corr vs short del par).
Ver [[batch3-adx-squeezeshort]] (donde el edge grueso SÍ era ortogonal) y [[indicadores-nuevos-batch1-sqz-vtx]].
