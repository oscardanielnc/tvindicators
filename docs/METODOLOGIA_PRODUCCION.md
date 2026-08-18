# Metodología de producción: embudo, asignación de capital y leverage

**Fecha:** 2026-06-19 · Define cómo pasan las estrategias de paper a real, cuánto capital
y apalancamiento reciben, y cómo se "pulen" sin engañarnos. Complementa `VALIDACION_Y_PRODUCCION.md`.

## 0) Filosofía

79 estrategias (64 cripto + 15 tradfi) en **paper son un embudo de recolección, NO el libro real**.
Solo operan con dinero real las que demuestren edge. Se pulen, se promueven las que maduran, se retiran
las que se degradan. **Mandan los resultados vivos, no el nombre ni la antigüedad.**

## 1) Embudo (paper → real)

```
79 escuchando (paper) → acumular trades → a los 20 trades: EVALUAR
   → pasa el gate → promover a real con peso pequeño
   → a los ~50 trades: peso pleno
   → se degrada (exp<0 con ≥gate trades) → retirar
```

- **Go-live v1:** ≥8 estrategias con >20 trades que pasen el gate, **Y** condiciones de cartera (abajo).
- **Roster rodante:** cada semana puede madurar otra de las 79; se promueve y se **rebalancean pesos**.

## 2) Gate de promoción — PRE-REGISTRADO (fijar antes de ver más datos)

Una estrategia pasa a real si en VIVO cumple TODO (no solo "20 trades y se ve bien"):
- **≥20 trades** cerrados (screening) · **≥50** para peso pleno.
- **Expectancia neta > 0** (después de fees + funding + slippage).
- **t-stat de la expectancia ≥ ~1.5–2** (que no sea ruido; con n=20 el IC del WR es ±~21%).
- **Ratio `live_exp / bt_exp` ≥ 0.30** (conserva ≥30% del edge del backtest).
- **PF live ≥ 1.2.**

**Condiciones de CARTERA para go-live (no solo por estrategia):**
- Equity combinada de paper positiva · Sharpe/DD de cartera aceptable.
- Las 8 **no son la misma apuesta** (penalizar correlación de PnL — ver `roster_optimizer.py`).
  Si 2 candidatas son muy similares, **descartar 1 y esperar** a otra distinta hasta completar 8.
- `GATE_PORT_MIN_TRADES=150` agregados · `GATE_PORT_MIN_CONFIRMED=8`.

**Cadencia de revisión:** el go-live se decide un día fijo (p.ej. domingo) con las que superaron 20 trades
y tienen buenos números. Las que superaron 20 pero con números flojos quedan **en espera**, se re-evalúan
la semana siguiente. Cada semana: promover nuevas, re-pesar las activas, y aplicar demotion (§4).

**Regla de DEMOTION (fijada):** se baja el peso de una estrategia si **expectancia < 0 con ≥40 trades**.
(No por una mala racha puntual — 40 trades es el umbral acordado para distinguir degradación de varianza.)

## 3) Disciplina de "pulido" — evitar el autoengaño (LO MÁS IMPORTANTE)

El objetivo es llevar cada estrategia a su mejor versión ajustando entrada/SL/TP/tiempo. Riesgo: si
ajustas mirando los trades que ya viste, **sobreajustas a la muestra de evaluación** e inflas la expectancia.
Reglas para que el aprendizaje sea honesto:

1. **No se aprende de 1 trade.** Con WR ~40% una pérdida es el resultado esperado, no una señal de fallo.
   Revisar por **lotes (~20 trades)** buscando *patrones en los perdedores*, no anécdotas.
2. **Todo ajuste de parámetro se re-valida en backtest out-of-sample** antes de aplicarlo en vivo.
3. **Al cambiar un parámetro, el contador de 20 trades se REINICIA** (la versión nueva tiene 0 evidencia viva).
4. Patrones que SÍ son señal (vienen del contexto que ya guardamos): pérdidas que se concentran en
   funding alto, en cierta hora (`entry_hour`), en chop (`entry_atr_pct`), contra-tendencia
   (`entry_trend_dist`), régimen adverso (`entry_regime_ok`). Ej. concreto: **LINK (S39) y JUP (S51)**
   pierden solo en bear → merecen filtro de régimen (gatear long a BTC-bull). Eso es un ajuste legítimo.

## 4) Asignación de capital (pesos por estrategia)

Idea base del proyecto: **más capital a la mejor estrategia.** Refinada para no concentrar en la que
tuvo suerte temprana:

- Ponderar por **edge ajustado a riesgo** (expectancia/σ ≈ Sharpe, o fracción de Kelly recortada),
  **no** por WR crudo ni profit bruto. "Gana poquito siempre" puede ser peor que "gana 50% pero grande".
- **Penalizar correlación:** dos longs de alts correlacionadas son *una* apuesta → no doble peso.
- **Tope por estrategia** (~20–25%) y **shrinkage hacia equal-weight** (las estimaciones tempranas son ruidosas).
- Ejemplos de la dirección correcta (a calibrar con backtest, no a ojo):
  - 8 iguales → 12.5% c/u. Entran 2 iguales → 10% c/u.
  - 2 nuevas el doble de buenas → ~2/12 c/u, resto ~1/12 (derivado del presupuesto de riesgo, con tope).

## 5) Apalancamiento dinámico por moneda (objetivo: riesgo constante, no profit constante)

Premisa del proyecto: el leverage NO es fijo, depende de la volatilidad de la moneda (5x en BTC ≠ 5x en SOL).
Se busca un movimiento objetivo (~5%) por operación. Por eso se guarda **% ganancia SIN apalancar**.

**Corrección clave (riesgo, no profit):** apalancar para amplificar un edge pequeño **también amplía la
distancia al stop**. Si BTC mueve 0.5% y le pones 10× para sacar 5%, una excursión adversa normal te
liquida. Lo correcto es fijar el leverage para que **el riesgo por trade sea constante**:

```
leverage_moneda  ≈  riesgo_objetivo_por_trade(% capital)  /  (dist_al_stop_en_% del precio)
dist_al_stop ≈ ATR_mult × ATR% de la moneda     (ya guardado: entry_atr_pct)
```

Resultado parecido a la intuición (menos leverage en SOL volátil, más en BTC tranquilo) pero **dimensionado
por ATR/stop, no por el retorno esperado** → no vuela la cuenta en las colas. Además:
- **Tope de leverage por moneda** (límites de exchange + buffer de liquidación).
- El **funding crece con el nocional** → leverage alto en monedas de funding caro se come el edge.

### 5.1) R (riesgo por trade) — calibrado al 25% maxDD anual

**R es la única perilla maestra.** Calibrado con `calibra_R.py` (carteras de 8-10 estrategias, sizing
equal-R, bootstrap por bloques que preserva correlación, 3000 caminos/año):

| R/trade (N=8) | DD esperado | DD p95 | DD peor | Retorno anual med. | P(DD>25%) |
|---|---|---|---|---|---|
| **0.5% (actual)** | −7% | −14% | −33% | +47% | 0% |
| 0.75% | −9% | −20% | −46% | +71% | 2% |
| 1.0% (full-Kelly) | −12% | −25% | −68% | +94% | 5% |

**Decisión: R = 0.5% por trade AHORA** (medio-Kelly). Razones: el backtest es optimista (in-sample,
survivorship, 40/56 con t<2) → colchón para degradación viva; el 25% queda como **techo de cola, no caso
normal** (clave en copy-trading: si rompes 25%, todos los seguidores rompen 25% a la vez); aun así +47%/año.

**R es incrementable a futuro** (el usuario lo quiere). Subirlo hacia 0.75% **solo después** de que el vivo
confirme que el edge se sostiene, y **nunca dejar la sim p95 por encima de ~15-18%** para que el 25% siga
siendo cola. R se re-evalúa cada semana al cambiar el roster (más estrategias descorrelacionadas → permiten
más R al mismo DD).

## 6) Por qué importa el presupuesto de riesgo de cartera (lección del análisis de ruina)

En paper, las 79 sin tope llegan a **~18× de exposición bruta** en picos (37 posiciones a la vez) → días de
−40% y cola de ruina ~5%. En producción solo operan 8–10, pero **el mismo apilamiento reaparece a menor
escala** si cada una usa leverage dinámico sin un **presupuesto de riesgo común**. Por eso §4 (pesos) y §5
(leverage por riesgo) deben combinarse con un **tope de riesgo agregado** (suma de riesgos por trade ≤ X%
del capital). Validamos con vol-parity; hay que operar con un esquema equivalente, no flat-uncapped.

## 7) Datos que el CSV/eval debe exponer para soportar todo esto

Ya capturados por trade (`db.py`/`engine.py`, 15/06): MAE/MFE en %/R, contexto de entrada (ATR%, dist SMA200,
hora, régimen vol, régimen B-X, funding), slippage. **Falta agregarlos por estrategia en el CSV de evaluación:**
- **% movimiento medio sin leverage** (insumo del §5).
- **MAE/MFE medios** (tunear SL/TP del §3).
- **Hold medio y % de salidas por timeout** (tunear tiempo).
- **Motivo de salida** (stop / target / timeout).
- **Contexto promedio separado ganadores vs perdedores** (ver *por qué* falla).
- **Ratio live/bt + t-stat** (gate del §2).

## 8) Producto copy-trading

El cliente **no elige estrategias**, solo el modo de copia: monto fijo por operación o **proporcional al
líder** (casi todos eligen proporcional). Por eso **todo se razona en % del capital total**, no en $ absolutos.
Implicación: el DD del cliente = el DD del líder, simultáneo → el 25% es techo de cola, DD esperado ~7-10%.

## 9) Sizing en la fase actual (paper)

- **$100 fijo por estrategia** en paper por ahora (= medir edge individual limpio; los pesos relativos no
  se pueden decidir hasta saber quiénes entran). **Pero el leverage SÍ por riesgo desde ya** (R=0.5%, §5.1).
- $100-flat en paper mide edge **individual**, NO valida la curva de cartera. Antes del go-live real:
  **sim de cartera** con las 8 elegidas, sus pesos (§4) y R (§5.1), verificando el 25% a nivel cartera.
- Al promover: empezar con monto bajo y subir con la confianza/muestra (el λ del shrinkage, §4).

## Estado y próximos pasos
- Fase actual: recolección en paper. No tocar señales/contador por n=1.
- ✅ **(19/06) Filtro de régimen LINK(S39)/JUP(S51):** `_btc_bull()` (BTC close diario > SMA200), gatea su
  entrada a bull. `data.py` soporta tf `1d`. Su contador de 20 trades se reinicia (lógica de entrada nueva).
- ✅ **(19/06) Sizing por riesgo R=0.5%:** `engine._open` deriva leverage del ATR de entrada
  (`leverage = R·cap/(dist_stop·margen)`, cap `MAX_LEVERAGE=10`, margen $100 fijo). `config.RISK_PER_TRADE`,
  `config.MAX_LEVERAGE`. Da 1.5×–4.4× en el roster (antes 5× plano sobre-arriesgaba las alts volátiles).
- ✅ **(19/06) CSV de evaluación enriquecido** (`/api/evaluation.csv`): + `t_stat`, `move_nolev`,
  `avg_win/avg_loss`, `avg_mae_r/avg_mfe_r`, `hold_bars`, `pct_sl/pct_timeout/pct_flip`, y contexto
  ganador-vs-perdedor (`fund_w/l`, `hour_w/l`, `atr_w/l`, `trend_w/l`, `regok_w/l`).
- Cuando haya 8: pesos §4, sim de cartera §9, tope de riesgo §6.
- Antes de cada ajuste de parámetros: re-validar OOS y reiniciar contador (§3).
