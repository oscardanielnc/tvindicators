# Veredicto — Réplica honesta de la estrategia S/D 1m ("Forex Education Live")

**Fecha:** 2026-06-14 · **Datos:** Binance perps 1m, 2025-01-01 → 2026-06-15 (763k velas/moneda)
**Costos:** taker 0.045%/lado + slippage 0.02% = 13 bps ida-y-vuelta · **Split:** IS<2026-01 / OOS 2026

## TL;DR
La entrada **NO tiene edge**. Las 50 combinaciones SL/TP pierden (~−13 bps/trade = el costo de
operar → **gross edge ≈ 0**, la entrada es una moneda al aire). El win-rate alto (ETH 85.9% sin
stop) es **real pero un artefacto**: TP chico que el ruido toca + nunca marcar perdedores. Cola
**catastrófica**: un trade de ETH −17% (se fue 29% en contra). **IS ≈ OOS** y **opt ≈ pess** →
robustamente malo, ni sobreajuste ni artefacto intrabar.

## Qué se replicó (validado contra 5 capturas en vivo del 14/06/2026)
- **TREND** = pendiente de EMA(50) — filtro maestro.
- **Entrada** = ruptura de micro-rango (10 velas) a favor de tendencia (momentum). RSI = cosmético.
- **Validación de fidelidad:** la réplica dispara el **Sell de BTC a 12:31 UTC** y el **Buy de ETH a
  19:15 UTC** que el usuario capturó hoy — sin información de esos momentos. Entrada FIEL.
- **Exit del stream** (TP = zona opuesta, marcado en hindsight, SIN SL) → reemplazado por exits
  MECÁNICOS (TP/SL fijos + barrido) porque el del stream no es operable (no se puede "fallar" un TP
  que solo se dibuja cuando el precio llega).

## Resultados clave (ret_pess, conservador)
| Moneda | Mejor config (por expectancy) | n | WR | exp | PF | Sin stop (estilo stream) |
|--------|-------------------------------|---|----|----|----|--------------------------|
| BTC | TP 0.50% / SL 0.10% | 26,585 | 16.8% | **−13.0 bps** | 0.32 | WR 78.1%, exp −13.8 bps, peor −5.8% |
| ETH | TP 0.50% / SL 0.50% | 15,928 | 49.9% | **−12.5 bps** | 0.59 | WR 85.9%, exp −13.1 bps, **peor −17.0%** |

- Ganador medio (sin stop) **+7 bps** vs perdedor medio **−88 (BTC) / −136 (ETH) bps** → 1 perdedor
  se come 12–19 ganadores.
- **MAE:** para capturar +0.10%, el adverso p90 es 0.40% (BTC) / 0.51% (ETH) → se arriesga 4–5× el
  premio. La intuición "1/5" está invertida.

## Por qué el stream parece 80–90% ganador (mecanismo, confirmado por el usuario)
1. El **TP se marca en retrospectiva** cuando el precio llega → imposible "fallar".
2. **Sin SL** → los perdedores nunca se marcan ni se cuentan.
3. **TP chico** que el ruido de 1m toca casi siempre (en 4h el precio roza ±0.10% el 85–90% del tiempo).

Con costos reales y contabilidad honesta de las pérdidas: **−13 bps por trade.**

## Caveat (límite del test)
La réplica dispara muchas más señales que el canal (él es más selectivo, ~1 por swing). No descarta
al 100% que una regla de selección oculta agregue edge — pero gross≈0 en TODAS las celdas lo hace muy
improbable sin una señal predictiva adicional que no aparece en los frames. Check pendiente opcional:
variante selectiva (1 trade/swing o exigir toque de zona) a la frecuencia del canal.

## Tests adicionales (pedido del usuario): selectividad, SL cercano, multi-TF
**Ninguna de las 3 ideas rescata el edge. CERRADO.** (ver `backtest_sd_multi.md`)
- **Selectividad** (event + cooldown a ~5.5 trades/día, como el canal): expectancy sigue −13 bps. La frecuencia no era el problema.
- **SL más cercano**: SÍ doma la cola (1h: peor trade −14% → −2.4%) pero NO la expectancy (sigue ~−13 bps en las 8 celdas). Cambia el camión por muerte de mil cortes.
- **TF mayor**: edge BRUTO sube de ~0 (1m/5m/15m) a **+8 bps (1h)** — es la sombra del trend-following real — pero NO alcanza: neto −5 bps tras 13 bps de costo, e IS (3.5 años) negativo (el OOS+ es muestra chica = ruido).
- **Contraste decisivo**: el roster S1-S21 saca +40 a +300 bps BRUTOS en 1h con entradas refinadas. Esta entrada cruda (EMA+breakout) capta una astilla. Perseguir el 1h = reconstruir una versión peor de lo que ya hay en producción. Nada que agregar.

| coin·TF | tr/día | exp neto | gross | IS/OOS |
|---|---|---|---|---|
| BTC 1m | 5.7 | −12.6 | +0.4 | −12/−13 |
| BTC 1h | 0.8 | −4.7 | +8.3 | −6/+6 |
| ETH 1m | 5.5 | −12.0 | +1.0 | −12/−13 |
| ETH 1h | 0.7 | −5.2 | +7.8 | −10/+34 |

## Lección general (reusable — para no repetir el trabajo)
Aplica a CUALQUIER servicio de señales (YouTube / Telegram / Discord) con win rate "imposible" (>75%):

**Red flags de win-rate falso:**
1. El TP aparece SOLO cuando el precio llega (marcado en retrospectiva) → imposible "fallar".
2. Nunca se muestra un SL ni una operación perdedora → los perdedores no se cuentan (supervivencia).
3. TP minúsculo (en 1m el precio roza ±0.1% casi siempre) → "aciertos" triviales sin valor predictivo.
4. "90% de aciertos a 5:1 R:R" es matemáticamente imposible (+4.4R/trade); si los números implican
   lo imposible, una premisa está rota — casi siempre: "sin stop → perdedores no contados".

**Cómo testearlo honesto (5 pasos, harness ya en el repo):**
1. Replica SOLO la entrada comprometida (la flecha), nunca el exit marcado en hindsight.
2. Valida la entrada contra capturas reales con timestamp (¿dispara cuando dispara el stream?).
3. Agrega costos taker reales + SL real + banda intrabar optimista/pesimista.
4. Mide el **edge BRUTO = neto + costo**. Si gross ≈ 0, es ruido sin importar el win rate.
5. Revisa la COLA (5 peores) y el split IS/OOS. WR alto + cola fea + gross≈0 = aplanadora.

**Atajo de datos:** `python fetch_1m.py <tf> <since> <coins>` baja cualquier TF al store Oscilion.

## Artefactos
`sd_replica.py` (motor v2) · `valida_sd.py` (validación de frames) · `backtest_sd.py` (backtest 1m) ·
`backtest_sd_multi.py` (multi-TF) · `backtest_sd_matrix.md` + `backtest_sd_multi.md` (resultados) ·
`fetch_1m.py` (datos, genérico por TF).
