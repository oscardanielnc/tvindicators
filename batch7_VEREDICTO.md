# Veredicto — Batch 7: KVO + S/R High Volume Boxes + ICT Turtle Soup (baja convicción)

**Fecha:** 2026-06-15 · store 52 monedas 1h · costos+funding · IS<2025/OOS≥2025. 3 indicadores del usuario con baja convicción → evaluación honesta.

## Resumen
| Indicador | Veredicto |
|-----------|-----------|
| **KVO (Klinger Volume Oscillator)** | ❌ descartado — oscilador de volumen, redundante con momentum; varios survivors con IS débil u OOS decayente |
| **S/R High Volume Boxes (ChartPrime)** | ✅ **el ganador** — 5 promovidos (S52-S56) |
| **ICT Turtle Soup (Flux Charts)** | ❌ descartado — sin edge |

## 1) KVO — descartado
Cruce KVO/Trigger. Algunos survivors pero el patrón se repite del batch 4: volumen en momentum =
redundante. Varios con IS débil (ATOM 31, ADA 12) u OOS decayendo (AVAX-L OOS 7). No aporta clase nueva.

## 2) S/R High Volume Boxes — ✅ promovido (S52-S56)
Pivotes confirmados por delta-volumen definen S/R; señal = ruptura. Sweep 52 monedas (gate duro) →
21 survivors, SRB la parte fuerte. Validación (sensibilidad lookback/vol_len + corr):
| Setup | exp/PF | IS / OOS | sens_min | corr roster | corr par |
|-------|--------|----------|----------|-------------|----------|
| FET-SRB-L | 219/1.85 | 228 / 206 | +134 | −0.07 | 0.28 vs S50 |
| DOGE-SRB-L | 171/1.98 | 220 / 113 | +23 | 0.11 | nuevo |
| ARB-SRB-S | 160/1.96 | 180 / 141 | +29 | 0.04 | −0.00 vs S31 |
| ALGO-SRB-L | 109/1.59 | 79 / 174 | +88 | 0.02 | nuevo |
| INJ-SRB-L | 99/1.43 | 113 / 72 | +54 | 0.04 | nuevo |
Todos robustos a sensibilidad, corr ~0 vs roster, y los del mismo par (FET 0.28, ARB 0.00) NO redundantes.
4 longs + 1 short → mejoran el balance. Descartado UNI-SRB-L (frágil a parámetros).

## 3) ICT Turtle Soup — ❌ descartado (sin edge)
Fade de barrido de liquidez HTF + MSS, TP/SL dinámico R:R 0.9. Backtest nativo en 1h (HTF 4h), costos+funding:
**Agregado: n=8870, WR 52%, exp −23.7 bps, PF 0.95, edge BRUTO −10.7 bps** (negativo antes de costos).
IS −45 bps / OOS +5.8 (ruido). Solo **1/51 monedas** (LTC) pasa un gate robusto = azar de multiple-comparison.
El R:R 0.9 (TP<SL) con WR 52% no cubre costos. Misma lección que el S/D de YouTube: WR≈50% + R:R<1 + costos = aplanadora.

## Impacto
Roster 51→56. Portafolio 1×: Sharpe **3.86→4.07**, maxDD **−2.7→−2.2%**, +2.1%/mes. SRB diversifica de verdad.

## Artefactos
`poc_batch7.py` (KVO+SRB sweep) · `valida_batch7.py` (SRB sensibilidad+corr) · `poc_turtlesoup.py` (ICT, motor nativo).
Lección: de 3 indicadores de baja convicción, 1 aportó (SRB, estructura+volumen), 1 redundante (KVO), 1 sin edge (Turtle Soup). La baja convicción del usuario fue acertada en 2/3. Ver [[batch4-volumen-redundante]], [[youtube-1m-sd-confluence-replica]].
