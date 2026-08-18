# Veredicto — Batch 6: Zero Lag Trend Signals (AlgoAlpha)

**Fecha:** 2026-06-15 · store 52 monedas 1h · costos+funding · motor de continuación · gate DURO (IS>0 Y OOS>0).

## Indicador (réplica Pine-fiel)
ZLEMA = `ema(close + (close - close[lag]), length)`, lag=⌊(length−1)/2⌋, length=70. Banda =
`highest(ATR(length), length*3) * mult` (mult=1.2). Estado `trend`: crossover(close, ZLEMA+banda)→+1,
crossunder(close, ZLEMA−banda)→−1 (persiste). Dos señales:
- **ZLflip:** `trend` cruza 0 (cambio de tendencia).
- **ZLentry:** close re-cruza la ZLEMA en la dirección de la tendencia establecida (pullback re-entrada).

## TL;DR — buen indicador; la variante ENTRY es la robusta
Sweep 52 monedas → **38 setups** pasan el gate duro, muchos con edge GRUESO (130-290 bps) e IS≈OOS sólido
(mejor balance que los osciladores del batch 5). Como todo trend-signal, en monedas ya cubiertas es
parcialmente redundante; el valor limpio está en **monedas nuevas**. Validación (sensibilidad length 50/70/90
+ mult 1.0/1.2/1.5 + corr): **la `ZLflip-L` es FRÁGIL a parámetros** (ATOM −101, LDO −12, CRV −8); la
**`ZLentry` es ROBUSTA**.

## Promovibles (robustos a sensibilidad + corr ~0 vs roster y entre sí; 6.9/7 apuestas efectivas)
| # | Setup | Filtro | exp/PF | IS / OOS | sens_min | Nota |
|---|-------|--------|--------|----------|----------|------|
| 1 | **FIL-ZLentry-L** | sweep6 | 190/2.17 | 121 / 298 | +112 | moneda nueva, **long**, el más fuerte |
| 2 | **NEO-ZLentry-S** | sweep6+trend | 225/3.19 | 231 / 219 | +65 | fat, balanceado; NEO-L=S40 (lado opuesto) |
| 3 | **STX-ZLentry-S** | sweep6 | 98/1.52 | 109 / 85 | +53 | moneda nueva, balanceado |
| 4 | **CRV-ZLentry-S** | sweep6+trend | 106/1.51 | 78 / 162 | +37 | moneda nueva |

**Descartados:** ZLflip-L (CRV/LDO/ATOM/XLM/WIF) por fragilidad a length/mult; resto por redundancia con
shorts del mismo par ya en roster (FLOW/RUNE/GRT/EGLD/ARB ZLentry-S vs sus shorts existentes).

## Caveats
- n bajo en NEO/CRV (43-45) → estimación ruidosa; mitigado por sensibilidad positiva e IS≈OOS. Peso ½, observar.
- 3 de 4 son shorts (roster ya short-heavy); pero monedas nuevas y corr ~0 → diversifican de verdad. FIL aporta long.

## Recomendación
Promover los **4 robustos** (FIL-L, NEO-S, STX-S, CRV-S) como S45-S48 (role 0.5). Requiere replicar la
ZLEMA + estado trend en `tvbot/indicators.py`. Solo se usa la variante ENTRY (la FLIP no se promueve).

## Artefactos
`poc_batch6.py` (sweep + gate duro) · `valida_batch6.py` (sensibilidad length/mult + corr). Lección:
Zero Lag ENTRY (pullback en tendencia) es un buen generador de señales; el FLIP crudo es frágil. Ver
[[batch3-adx-squeezeshort]] (edge grueso) y la pauta de que monedas nuevas dan la diversificación real.
