# Consolidado de Estrategias Validadas — tvindicators
**Generado:** 12/06/2026 · Datos: Binance perps 2023-06 → 2026-06 · Costos maker 0.02%/lado (stops a taker+slip) · Funding real incluido · IS ≤2025-12 / OOS 2026 · Sin apalancamiento (1×)

## Roster final (9 estrategias · 7 monedas · 6 long / 3 short)

| # | Estrategia | TF | Estado | Tr/mes | WR | Gana en | Pierde en | Exp/trade | CAGR | MaxDD | PF | Sharpe | Años+ | 2026 | Peso 💼 | $/trade* | $/mes* |
|---|------------|----|--------|--------|----|---------|-----------|-----------|------|-------|----|--------|-------|------|---------|----------|--------|
| 1 | TRX LONG · B-Xtrender | 1h | ✅ Titular | 18.3 | 38% | 48h | 14h | +0.31% | +80% | −22% | 1.46 | 1.39 | 4/4 | +24% | 10% | $3.13 | $57 |
| 2 | TRX LONG · Trend Meter | 1h | ✅ Titular | 16.5 | 37% | 48h | 16h | +0.27% | +56% | −18% | 1.40 | 1.13 | 4/4 | +20% | 11% | $2.73 | $45 |
| 3 | TRX LONG · Supertrend+HACOLT+Ribbon | 15m | ✅ Titular | 22.1 | 40% | 16h | 6h | +0.19% | +56% | −22% | 1.58 | 1.47 | 4/4 | +14% | 15% | $1.86 | $41 |
| 4 | SUI SHORT · B-Xtrender+régimen | 1h | ✅ Titular | 6.7 | 41% | 48h | 18h | +0.72% | +59% | −51% ⚠️ | 1.40 | 1.15 | 4/4 | +94% | 11% | $7.25 | $49 |
| 5 | LTC SHORT · Supertrend+Donchian | 1h | ✅ Titular | 5.0 | 38% | 48h | 16h | +0.47% | +26% | −25% | 1.38 | 0.89 | 4/4 | +2% | 17% | $4.68 | $23 |
| 6 | XRP LONG · Supertrend+HACOLT | 1h | ✅ Titular | 5.8 | 39% | 72h | 32h | +0.95% | +60% | −39% | 1.66 | 0.95 | 4/4 | +16% | 7% | $9.53 | $56 |
| 7 | AVAX LONG · Supertrend+Donchian+HACOLT | 15m | ✅ Titular | 19.9 | 37% | 18h | 6h | +0.25% | +60% | −33% | 1.28 | 1.17 | 4/4 | +27% | 10% | $2.49 | $50 |
| 8 | ETH SHORT · B-Xtrender+Donchian | 1h | 🟡 Suplente ½ | 6.4 | 32% | 48h | 18h | +0.30% | +19% | −28% | 1.26 | 0.69 | 3/4 | +19% | 8% | $3.00 | $19 |
| 9 | BTC LONG · Ribbon+BXreg+Supertrend | 1h | 🟡 Suplente ½ | 4.6 | 36% | 48h | 14h | +0.45% | +25% | −17% | 1.57 | 1.13 | 4/4 | +8% | 12% | $4.54 | $21 |

\* $/trade y $/mes = con **$1,000 dedicados solo a esa estrategia** (promedio histórico, no garantía).
"Gana en / Pierde en" = duración promedio del trade ganador / perdedor. No hay TP fijo: perdedores salen por ATR-stop (2×ATR14), ganadores corren hasta timeout 48h o flip del Supertrend.

## Portafolio combinado (pesos vol-parity, suplentes a ½)

| Leverage | CAGR | MaxDD | Mensual medio ($1,000) | Peor mes | $1,000 → 33 meses |
|----------|------|-------|------------------------|----------|--------------------|
| 1× | +61% | −7.3% | +4.0% (~$40) | −6.0% | $3,695 |
| 2.12× (ancla DD−15%) | +164% | −15% | +8.7% (~$87) | −12.5% | $14,461 |
| 2.90× (ancla DD−20%) | +264% | −20% | +12.0% (~$120) | −16.7% | $35,105 |
| 4.59× (ancla DD−30%) | +595% | −30% | +19.4% (~$194) | −25.3% | $209,264 |

Sharpe 2.47 · 79% meses positivos · Por año: 2023 +20% / 2024 +90% / 2025 +32% / 2026 +23% (a 1×).

## Advertencias (leer siempre)
1. Números de backtest = **techo, no expectativa**: 9 ganadores elegidos entre ~6,900 tests sobre la misma historia. En vivo se suele conservar 30-50% del edge.
2. El DD vivo suele superar al del backtest (~2×). Calibrar leverage a −30% backtest puede significar −60% real. Recomendado: arrancar 1-1.5×, máximo 2× tras paper trading.
3. Expectativa realista en vivo: **3-6% mensual a ~2×** (vs Kepler real: ~1%/mes a DD−10%).
4. Concentración: las 3 TRX-L correlacionan 0.74-0.85 (≈1.5 apuestas, 35% del peso). SUI-S depende de que SUI siga estructuralmente débil.
5. Validación pendiente: **paper trading 4-8 semanas** en VM (gate: ≥30 trades, expectancy>0, DD≤1.5× esperado) antes de dinero real.

## Reglas exactas por estrategia (spec para el bot)
- Entrada: siempre al OPEN de la vela siguiente a la señal (sin look-ahead). Orden límite (maker).
- S1: círculo verde B-Xtrender (T3(osc,5) gira arriba) con T3<0 → long TRX 1h. Salida: ATR-stop 2× o timeout 48h.
- S2: los 3 Trend Meters se alinean verdes (MACD 8/21/5 hist>0 + RSI13>50 + RSI5>50) → long TRX 1h. Salida: igual S1.
- S3: flip alcista Supertrend(10,3) + HACOLT=1 + Ribbon≥8/10 → long TRX 15m. Salida: flip bajista ST.
- S4: círculo rojo B-X con T3>0 + régimen B-X<0 → short SUI 1h. Salida: ATR-stop/timeout 48h.
- S5: flip bajista ST + Donchian(20)=−1 → short LTC 1h. Salida: ATR-stop/timeout.
- S6: flip alcista ST + HACOLT=1 → long XRP 1h. Salida: flip bajista ST.
- S7: flip alcista ST + Donchian=1 + HACOLT=1 → long AVAX 15m. Salida: flip bajista ST.
- S8: círculo rojo B-X T3>0 + Donchian=−1 → short ETH 1h. Salida: ATR-stop/timeout. (½ peso)
- S9: Ribbon completa 10/10 alcista + BXreg>0 + ST=up → long BTC 1h. Salida: ATR-stop/timeout. (½ peso)
