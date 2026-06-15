# Consolidado de Estrategias Validadas — tvindicators
**Regenerado:** 15/06/2026 (`gen_consolidado.py`) · Datos: Binance perps store completo (52 monedas, ~2022→2026-06) · Costos maker 0.02%/lado (SL a taker 0.045%+slip 0.02%) · **Funding real incluido** · Sin apalancamiento (1×) salvo donde se indica.

> Métricas **recalculadas sobre el store actual** (más historia que el baseline 2023-06 original). Por eso exp/PF pueden diferir levemente del `BACKTEST_REF` de `tvbot/strategies.py` (ese se fijó en la validación original y es el que usa el frontend para comparar live vs backtest). El método y el motor de salida son idénticos al bot (`run_f`, paridad `engine.py`).

## Roster (44 estrategias · 7 titulares + 37 suplentes · 18 long / 26 short)

| # | Estrategia | TF | Lado | Rol | Tr/mes | WR | exp(bps) | PF | CAGR 1× | MaxDD 1× | Años+ | Indicador clave |
|---|------------|----|------|-----|--------|----|----------|----|---------|----------|-------|-----------------|
| S1 | TRX-L B-Xtrender | 1h | L | Titular | 1.8 | 44% | 142 | 3.69 | +27% | −6% | 4/4 | B-Xtrender |
| S2 | TRX-L Trend Meter | 1h | L | Titular | 25.1 | 38% | 23 | 1.64 | +84% | −11% | 4/4 | Trend Meter |
| S3 | TRX-L ST+HAC+Ribbon | 15m | L | Titular | 22.1 | 40% | 19 | 1.60 | +59% | −22% | 4/4 | Supertrend |
| S4 | SUI-S BX+régimen | 1h | S | Titular | 6.8 | 41% | 69 | 1.38 | +55% | −53% ⚠️ | 4/4 | B-Xtrender |
| S5 | LTC-S ST+Donchian | 1h | S | Titular | 5.0 | 37% | 45 | 1.36 | +25% | −25% | 4/4 | Supertrend |
| S6 | XRP-L ST+HACOLT | 1h | L | Titular | 2.9 | 42% | 199 | 2.43 | +68% | −23% | 4/4 | Supertrend |
| S7 | AVAX-L ST+Don+HACOLT | 15m | L | Titular | 19.9 | 38% | 26 | 1.30 | +64% | −33% | 4/4 | Supertrend |
| S8 | ETH-S BX+Donchian | 1h | S | ½ | 3.0 | 39% | 63 | 1.48 | +21% | −24% | 4/4 | B-Xtrender |
| S9 | BTC-L Ribbon+BXreg+ST | 1h | L | ½ | 4.7 | 36% | 48 | 1.61 | +28% | −17% | 4/4 | Donchian Ribbon |
| S10 | DOT-S BX+Don+barrido | 1h | S | ½ | 2.3 | 43% | 79 | 1.64 | +22% | −22% | 3/4 | B-Xtrender |
| S11 | ADA-S BX+rég+tend+vol | 1h | S | ½ | 3.0 | 45% | 66 | 1.39 | +21% | −19% | 3/4 | B-Xtrender |
| S12 | ADA-S BX+Don+barrido | 1h | S | ½ | 1.6 | 40% | 53 | 1.38 | +9% | −24% | 3/4 | B-Xtrender |
| S13 | DOT-S ST+Don+tendencia | 1h | S | ½ | 3.2 | 37% | 49 | 1.35 | +17% | −27% | 3/4 | Supertrend |
| S14 | XLM-L TM+rég+tend+vol | 1h | L | ½ | 4.8 | 32% | 103 | 1.98 | +53% | −33% | 4/5 | Trend Meter |
| S15 | RUNE-L ST+Don+HAC | 1h | L | ½ | 1.7 | 46% | 209 | 1.91 | +36% | −51% ⚠️ | 5/5 | Supertrend |
| S16 | IMX-L ST+Don+HAC+vol | 1h | L | ½ | 1.3 | 46% | 150 | 1.69 | +19% | −29% | 4/4 | Supertrend |
| S17 | FLOW-L ST+HAC+vol | 1h | L | ½ | 1.5 | 47% | 145 | 1.68 | +22% | −32% | 4/5 | Supertrend |
| S18 | EGLD-S BX+barrido | 1h | S | ½ | 2.3 | 42% | 121 | 1.84 | +34% | −18% | 4/5 | B-Xtrender |
| S19 | FET-S BX+Don+barrido | 1h | S | ½ | 2.7 | 42% | 100 | 1.51 | +28% | −23% | 3/4 | B-Xtrender |
| S20 | APT-S ST+Don+tendencia | 1h | S | ½ | 2.2 | 41% | 97 | 1.56 | +24% | −31% | 4/5 | Supertrend |
| S21 | GRT-S BX+barrido+tend | 1h | S | ½ | 1.5 | 41% | 94 | 1.57 | +16% | −17% | 4/5 | B-Xtrender |
| **S22** | **ENA-L Squeeze+régimen** | 1h | L | ½ | 4.4 | 42% | **248** | 2.11 | +194% | −32% | 3/3 | **Squeeze Momentum** |
| **S23** | **SAND-S Vortex+régimen** | 1h | S | ½ | 7.4 | 43% | 72 | 1.46 | +69% | −30% | 5/5 | **Vortex** |
| **S24** | **WIF-L Squeeze+régimen** | 1h | L | ½ | 4.7 | 36% | **204** | 1.79 | +139% | −35% | 3/3 | **Squeeze Momentum** |
| **S25** | **SEI-S Vortex+barr+tend** | 1h | S | ½ | 3.4 | 44% | 103 | 1.54 | +42% | −29% | 3/4 | **Vortex** |
| **S26** | **ARB-S Vortex+barr+tend** | 1h | S | ½ | 3.9 | 41% | 74 | 1.46 | +33% | −39% | 3/4 | **Vortex** |
| **S27** | **RUNE-S Vortex+barr+tend** | 1h | S | ½ | 3.0 | 37% | 84 | 1.49 | +27% | −31% | 4/5 | **Vortex** |
| **S28** | **AVAX-S Vortex+barrido** | 1h | S | ½ | 5.7 | 38% | 71 | 1.46 | +50% | −35% | 3/4 | **Vortex** |
| **S29** | **BNB-L Squeeze+tend+vol** | 1h | L | ½ | 2.8 | 41% | 55 | 1.49 | +18% | −19% | 3/4 | **Squeeze Momentum** |
| **S30** | **INJ-L BB%b reversión** | 1h | L | ½ | 5.2 | 69% | 54 | 1.50 | +35% | −26% | 5/5 | **Bollinger %b (reversión)** |
| **S31** | **ARB-S ADX+tend+vol** | 1h | S | ½ | 1.2 | 49% | 197 | 2.13 | +27% | −17% | 4/4 | **ADX/DMI** |
| **S32** | **EGLD-S Squeeze+barrido** | 1h | S | ½ | 1.0 | 40% | 155 | 1.93 | +18% | −14% | 4/5 | **Squeeze Momentum (short)** |
| **S33** | **DOT-S ADX+barrido** | 1h | S | ½ | 1.4 | 47% | 130 | 1.97 | +21% | −11% | 3/4 | **ADX/DMI** |
| **S34** | **HBAR-S ADX+barrido** | 1h | S | ½ | 1.0 | 52% | 160 | 2.31 | +19% | −10% | 5/5 | **ADX/DMI** |
| **S35** | **FLOW-S Squeeze+barrido** | 1h | S | ½ | 0.9 | 45% | 126 | 1.72 | +13% | −19% | 4/5 | **Squeeze Momentum (short)** |
| **S36** | **AVAX-S ADX+barrido** | 1h | S | ½ | 1.3 | 56% | 224 | 2.87 | +38% | −15% | 3/4 | **ADX/DMI** (corr 0.39 con S28) |
| **S37** | **ORDI-L CMF+tend+vol** | 1h | L | ½ | 3.9 | 25% | 151 | 1.46 | +10% | −71% ⚠️ | 3/4 | **Chaikin Money Flow (vol)** |
| **S38** | **ORDI-L Force Index+régimen** | 1h | L | ½ | 7.6 | 33% | 115 | 1.47 | +37% | −64% ⚠️ | 3/4 | **Force Index (vol)** |
| **S39** | **LINK-L KST+barrido** | 1h | L | ½ | 3.5 | 34% | 89 | 1.54 | +34% | −27% | 3/4 | **KST (Pring)** |
| **S40** | **NEO-L AwesomeOsc+barr+tend** | 1h | L | ½ | 1.1 | 39% | 78 | 1.53 | +9% | −26% | 4/5 | **Awesome Oscillator** |
| **S41** | **ICP-S KST+régimen** | 1h | S | ½ | 5.6 | 43% | 74 | 1.46 | +51% | −24% | 5/5 | **KST (Pring)** |
| **S42** | **NEAR-S AwesomeOsc+barrido** | 1h | S | ½ | 1.8 | 47% | 116 | 1.80 | +25% | −15% | 5/5 | **Awesome Oscillator** |
| **S43** | **ALGO-S TSI+barr+tend** | 1h | S | ½ | 2.5 | 42% | 77 | 1.54 | +22% | −34% | 5/5 | **True Strength Index** |
| **S44** | **TAO-S AwesomeOsc+tend+vol** | 1h | S | ½ | 2.9 | 52% | 103 | 1.45 | +33% | −36% | 3/3 | **Awesome Oscillator** |

\* CAGR/MaxDD 1× = curva de equity de esa estrategia sola con capital dedicado (compone cada trade). No hay TP fijo: perdedores salen por SL (2×ATR; S2/S14 por 3×ATR), ganadores corren hasta flip del Supertrend / TM-opuesto o timeout 48h (atrstop).
**WR bajo (32-47%) es por diseño:** trend-following con *runners* — el edge es la asimetría (ganador medio ≫ perdedor medio), no el win-rate. Filosofía: pocas y buenas, baja frecuencia + ganancias asimétricas.
**Excepción S30** (única reversión a la media): perfil inverso — WR alto (69%), aciertos chicos, edge fino. Representante de la clase, peso bajo, en observación (ver `meanrev_VEREDICTO.md`).
**Batch 3 (S31-S36):** ADX/DMI shorts + Squeeze shorts — edge GRUESO (126-224 bps), baja frecuencia (~1/mes), validados OOS + sensibilidad + corr directa vs el short del mismo par (ver `batch3_VEREDICTO.md`).
**Batch 4 (S37-S38):** volumen (CMF, Force Index) en LONG sobre ORDI (moneda nueva, balance long/short). ⚠️ MaxDD 1× alto (ORDI muy volátil) — el peso ½/vol-parity lo diluye, pero vigilar. El volumen en SHORT resultó redundante con el momentum (no promovido; ver `batch4_VEREDICTO.md`).
**Batch 5 (S39-S44):** momentum-systems (KST, Awesome Osc, TSI) sobre monedas NUEVAS (LINK, NEO, ICP, NEAR, ALGO, TAO). Corr ~0 vs roster y entre sí (5.8/6 apuestas efectivas). En monedas ya cubiertas eran redundantes (ver `batch5_VEREDICTO.md`).

## Portafolio combinado (44 estrategias, pesos vol-parity 1/σ, `gen_summary.py`)

| Leverage | Mensual medio | MaxDD | CAGR | Sharpe | Meses+ |
|----------|---------------|-------|------|--------|--------|
| **1×** | **+2.0%** (~$20/$1k) | −3.1% | +28% | 3.64 | 86% |
| 2× (arranque prudente) | +4.1% (~$41) | −6% | — | | |
| 3× | +6.1% (~$61) | −9% | — | | |

Trades/mes total ≈ **195** · exp neto medio **106 bps/trade** (neto de ganancias y pérdidas) · WR medio 42%.
Por año (1×): 2022 +6% · 2023 +8% · 2024 +41% · 2025 +30% · 2026 +15% (a junio).
La expansión 9→44 mejora el perfil de riesgo: vs el roster viejo de 9 (Sharpe 2.47, DD−7.3% a 1×), ahora **Sharpe 3.64 y DD−3.1%** — mucha más diversificación por unidad de DD.

## Batch 1 de indicadores nuevos (S22-S29, promovidas 15/06/2026)
Squeeze Momentum (LazyBear) en longs + Vortex (VI+/VI−) en shorts — clases **ortogonales** al resto (que es MA-trend). Validadas: sweep 52 monedas → gate → OOS (IS<2025/OOS≥2025) → sensibilidad → corr ≤0.22 vs roster → impacto de portafolio (Sharpe 2.94→3.27). Corr media 0.06 entre ellas (7.1/8 apuestas efectivas). Ver `indicadores_nuevos_VEREDICTO.md`.
**Dedup cross-proyecto:** ninguna duplica estrategias de Oscilion (familia EMA/VWAP/ORB) ni de btc (descartado; usó BB-Squeeze ≠ LazyBear, nunca Vortex).

## Advertencias (leer siempre)
1. Números de backtest = **techo, no expectativa**: ganadores elegidos entre miles de tests sobre la misma historia. En vivo se conserva típicamente 30-50% del edge.
2. El DD vivo suele superar al del backtest (~2×). Calibrar a −30% backtest puede ser −60% real. Arrancar 1-1.5×, máximo 2× tras paper trading.
3. S22/S24 (ENA/WIF) tienen historia corta (monedas jóvenes, 3/3 años): CAGR 1× altísimo (+194%/+139%) es poco fiable como expectativa — peso ½ y observar.
4. Concentración residual: las 3 TRX-L correlacionan alto entre sí; varios alt-shorts comparten beta (aunque el libro de 16 shorts da 12 apuestas efectivas).
5. Validación pendiente: **paper trading** (gate: ≥30 trades/estrategia, expectancy>0, DD≤1.5× esperado) antes de capital real. Tanto este proyecto como Oscilion acumulan datos para una selección unificada futura.

## Reglas exactas
Spec completo por estrategia en `tvbot/strategies.py` (entradas s1-s29, salidas, filtros de convicción). Entrada siempre al OPEN de la vela siguiente a la señal (orden límite/maker, sin look-ahead). Referencia de backtest por estrategia para comparación live: `BACKTEST_REF` en el mismo archivo.
