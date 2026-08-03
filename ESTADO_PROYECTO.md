# Estado del proyecto — tvindicators
**Actualizado:** 2026-08-03 (sesión "auditoría de 52 días + fase de medición") · Fase: **MEDICIÓN** (paper en VM, sizing plano) ⏳

## Sesión 2026-08-03 — auditoría de 52 días vivos + giro a fase de MEDICIÓN (DESPLEGADO)
**Veredicto de la auditoría (272 trades cerrados, 13/06–03/08):** equity 1000→926 (−7.4%), maxDD
−28.4%, exp viva **−14.7 bps/trade contra +105 del backtest**, WR 37%, PF 0.90, **0/62 estrategias
confirmadas** (la que más tiene son 16 trades; el gate pide 20).
- **La frase honesta:** t vs 0 = −0.85 (no se puede probar que pierda) pero **t vs +105bp = −6.9**
  → sí se rechaza que el edge del backtest sobreviviera. No es varianza, es fallo de transferencia.
- **No es ejecución ni costes:** reconcile 0 mismatches, fees 6 bps del nocional, PnL bruto también
  negativo (−34 USD). Lo que falló es el edge.
- **`entry_regime_ok` NO es un gate roto** — es una etiqueta de contexto que se graba en TODOS los
  trades (engine.py:240), no "el filtro disparó". Que los trades con régimen favorable rindan peor
  (−36 vs +22 bps) es un hallazgo sobre el poder predictivo del régimen, no un bug.
- **Concentración:** sin los 5 mejores trades el PnL es −244; sin los 5 peores, +10. 272 trades
  pero ~10 deciden el resultado.

**Cambios desplegados (premisa del usuario: en esta etapa NO importa el balance, importa MEDIR
qué estrategias son rentables; el leverage óptimo se calibra después, ya aprobada la estrategia):**
1. **Sizing plano** (`SIZING_MODE='flat'`, nocional constante). Con sizing por riesgo, cripto-short
   daba +88 USD con **0.0 bps/trade**: el dólar venía del leverage variable, no de la señal. Cada
   trade debe pesar igual para que el PnL estime el edge. El sizing por riesgo queda tras el flag.
2. **Tesis como unidad de decisión** (`tvbot/theses.py`, `/api/theses`): las 79 estrategias se
   agrupan en 6 apuestas económicas. Gate por tesis con **t-stat e IC95**, no solo PnL>0 — más
   exigente que el gate por estrategia, y baja las comparaciones múltiples de 79 hipótesis a 6.
3. **Shadow-logging de salidas** (`tvbot/shadow.py`, `/api/shadow`): por cada trade cerrado se
   recorren las MISMAS velas con otras reglas (stops 0.5/0.75/1.5R, TP 1/1.5/2/3R, breakeven,
   trailing). Contrafactual exacto, no una cota. **No toca la ejecución** — registra evidencia para
   decidir stops con datos OOS en vez de retrofit. Fidelidad verificada: la variante `base`
   reprodujo el retorno real con mediana +0.0 bps y 0/168 trades con desvío >25 bps.

**Lo que reveló el sizing plano el primer día — el resultado más importante de la sesión:**
| Tesis | n | exp (bps) | t | veredicto |
|---|---|---|---|---|
| ORB de acciones | 11 | **+90.2** | +1.38 | acumulando — **le bastan ~24 trades** para confirmarse |
| Shorts de alts 1h | 162 | +0.4 | +0.02 | **edge demasiado fino para confirmarse nunca** (~2.1M trades) |
| Cripto intradía 15m/30m | 20 | −2.2 | −0.08 | sin edge |
| Longs de acciones (swing) | 46 | −10.9 | −0.33 | sin edge |
| Shorts de acciones | 4 | −43.4 | −0.16 | sin datos útiles |
| Longs de cripto | 29 | **−150.2** | **−3.65** | negativa (ya gateada desde 25/06) |

**Shorts de alts 1h era la tesis "prometedora" por sus +88 USD — medida en bps es plana.** Ese
+88 era un artefacto del leverage. Y con exp=+0.4 bps contra sd=320, confirmarla exigiría ~1100
años: la respuesta no es esperar sino **engordar la expectancia por trade** (salidas, filtros) o
abandonarla. `ORB de acciones` pasa a ser la única candidata con edge grueso — frágil (2 de sus
11 trades mandan) pero **barata de resolver**.

**Shadow (in-sample, 168 trades — orientativo, NO decisorio):** `tp2R` +25.8 bps sobre la salida
real (t=1.84) y `sl0.75R` +13.6 (t=1.90); `be1R` y `sl1.5R` empeoran. Consistente con MFE +1.50R
vs MAE −0.84R. **La decisión se toma con los trades posteriores al despliegue**, no con estos.

**Próximo paso:** acumular ~13 trades más de ORB de acciones y revisar `informe_tesis.py`.
Herramientas: `python informe_tesis.py` (VM) · `/api/theses` · `/api/shadow` · `backfill_shadow.py`.

---
**Actualizado antes:** 2026-06-25 (sesión "análisis con datos vivos + gate de régimen a todos los longs") · Fase: **DESPLEGADO en producción (paper trading en VM)** ✅

> **Cripto desplegado 2026-06-15; TradFi añadido 2026-06-16; metodología de producción + sizing por riesgo 2026-06-19; gate de régimen global 2026-06-25.**
> Roster: **64 estrategias cripto + 15 tradfi = 79** en sombra en la VM; backup/watchdog/alertas activos.
> **Datos vivos al 2026-06-25 (n=89 trades, ~5 días):** exp viva **−60.5 bps** (vs +107 backtest), WR 34%, maxDD **−25%**, 0/43 confirmadas.
> **Hallazgo clave:** longs de cripto −234 PnL vs shorts +73 → era **beta bajista de mercado, no fallo de señal** (BTC bear desde antes).
> **Desplegado HOY:** gate de régimen BTC extendido a **TODOS los longs de cripto** (`engine._manage_entries`); BTC bear → 0 longs ahora.
> Fase: **acumular datos + corregir semanal**, sin tradear sobre más pérdidas. Recalibración de sizing agregado APLAZADA (esperar n suficiente).
> VM acceso: `ssh -i sentinel-prod.key opc@213.35.121.9`. Metodología: `METODOLOGIA_PRODUCCION.md`.

## Sesión 2026-06-25 — análisis con datos VIVOS + gate de régimen global (DESPLEGADO)
Análisis honesto pedido por el usuario ("falla 2 de cada 1, ¿tiene futuro?"). Se accedió a la VM por SSH y se leyó la API viva (`localhost:8090`).
- **Aclaración de fondo:** WR bajo (34%) NO es el problema — es un sistema trend/momentum (diseñado para acertar ~33-42% con ganadores grandes). El juez es la **expectancia**, no el WR.
- **Datos vivos reales (n=89, desde 2026-06-20):** exp **−60.5 bps** (backtest +107), ratio live/bt **−0.56**, maxDD **−25.07%** (tocó el techo en 5 días), 0/43 confirmadas, avg MAE −0.92R / MFE +1.23R.
- **Diagnóstico por dirección (decisivo):** **LONGS 59 trades → −234.8 PnL** vs **SHORTS 30 trades → +72.6 PnL**. Los 8 peores son todos longs (ORDI/ENA/WIF/JUP/TSLA/MU), los 8 mejores todos shorts. **BTC estaba bear** (`close diario < SMA200`) → era beta de mercado, no alpha rota. (Revisa el diagnóstico previo del 2026-06-19 que decía "no es régimen": era cierto a n=38, pero a n=89 con BTC en bear sostenido el sesgo direccional es claro.)
- **Cambio desplegado (gate de régimen global):** en `engine._manage_entries`, todo long de cripto requiere `_btc_bull()` (BTC close diario > SMA200). Antes solo lo tenían S39/S51; ahora **todos**. Shorts NO se filtran. Los `stocks` (T*) **excluidos a propósito** (BTC no gobierna equities — necesitan su propio gate de índice SPY/QQQ, pendiente). Un solo punto de control. Aplicado en VM (servicio reiniciado, `active`) + repo local (compila). Backup VM: `engine.py.bak-20260625`.
- **Sizing — recomendación dada, ejecución APLAZADA por decisión del usuario:** el maxDD −25% en 5 días (modelo lo ponía como techo *anual*) viene de 3 fallos de `calibra_R.py`: (1) **sin tope de riesgo agregado** — N_concurrentes ×0.5% se apila sin límite; calibró para N=8 pero corre 43; (2) calibró solo sobre ganadoras (filtro `mean>0`); (3) bootstrap de bloques de 10d rompe la persistencia del bear. **El gate de hoy ya ataca (1) y (3)** al cortar la sangría de longs correlacionados. El cap de riesgo agregado y recalibrar R se harán **cuando haya estrategias con suficientes trades y prometedoras** (no ahora).
- **Plan de trabajo acordado:** acumular datos + corregir semanalmente lo accionable, evitando tradear sobre más pérdidas. NO añadir estrategias. NO tocar sizing completo todavía.

## Sesión 2026-06-19 — metodología de producción + sizing por riesgo (DESPLEGADO)
Revisión de los primeros 38 trades vivos (cuenta en negativo) → diagnóstico honesto + diseño de la ruta a real.
- **Diagnóstico (datos, no opinión):** las pérdidas vivas NO son de régimen — 8/10 longs perdedores tienen
  expectativa positiva en bear en backtest (`regime_split.py`); es **varianza de muestra n=1** (WR ~40%).
  Solo **LINK (S39) / JUP (S51)** son beta de bull → único ajuste justificado.
- **Riesgo de ruina** (`riesgo_ruina.py`): el sizing viejo (10%×5 plano, sin tope) llegaba a **~18× bruto**
  en paper. Decidido sizing por RIESGO: leverage = R·cap/(dist_stop·margen), margen $100 fijo.
- **R calibrado** (`calibra_R.py`): **R=0.5%/trade** (medio-Kelly) → maxDD anual p95 −14%, +47%/año, nunca rompe 25%.
  **R incrementable a futuro** tras confirmación viva. 25% maxDD anual = techo de cola (clave para copy-trading).
- **Implementado y desplegado (commit `cb94eed`):**
  - `engine._open`: leverage dinámico (1.5×–4.4× según ATR; antes 5× plano sobre-arriesgaba alts). `config.RISK_PER_TRADE=0.005`, `MAX_LEVERAGE=10`.
  - Filtro `_btc_bull()` (BTC close diario > SMA200) en S39/S51. `data.py` soporta tf `1d`. **Su contador de 20 trades se reinicia.**
  - CSV `/api/evaluation.csv` enriquecido: `t_stat`, `move_nolev`, `avg_win/loss`, MAE/MFE, `hold_bars`, motivo de salida, contexto ganador-vs-perdedor.
  - `reconcile`: S39/S51 excluidas (overlay BTC cross-asset, no reproducible bar-a-bar).
- **Metodología fijada** (en `METODOLOGIA_PRODUCCION.md`): embudo 79→real, gate (20 trades + t-stat≥1.5-2 + ratio≥0.3 + PF≥1.2),
  **demotion: bajar peso si exp<0 con ≥40 trades**, pesos por edge-ajustado-a-riesgo+correlación+tope+shrinkage (al tener 8),
  copy-trading proporcional (% del total), sim de cartera antes del go-live real.
- **A re-validar otro día:** (1) que trades NUEVOS muestren leverage variable (los pre-deploy son 5× viejo);
  (2) revisión semanal (domingo) de quién llega a 20 trades; (3) cuando haya 8 candidatas: pesos + sim de cartera + tope de riesgo agregado.

## Resumen en una línea
Bot de paper trading con **64 estrategias cripto + 15 tradfi (acciones, perps de Binance)**, motor con paridad
al backtest, API + dashboard con secciones separadas 🪙 Cripto / 📈 TradFi, y track record vivo que decidirá el capital real.

## Sesión 2026-06-16 — indicadores populares de TradingView (validación en paralelo)
Probados con disciplina (placebo/holdout IS-OOS + **anti-beta por-ticker** + costos reales). Lección transversal:
las métricas *pooled* (Sharpe/PSR altos) **mienten** si no se separa alpha de beta por símbolo.
- **GANADORES cableados:**
  - **SMC Swing Break of Structure [LuxAlgo]** → cripto bidireccional **S57–S64** (8; OOS Sharpe 1.47, PSR 99%,
    ambos lados ganan) + equity long-only **T12–T15** (NVDA/TSLA/AAPL/MU, anti-beta+).
  - **S/R Breaks [LuxAlgo] + Supertrend** (confluencia) → tradfi líquido **T7–T11** (TSLA/AAPL/NVDA long, MU/AMD short).
  - **NVDA ORB pre-market agitado** → **T6** (hipótesis del usuario invertida: el edge está en pre-market ACTIVO, no quieto).
- **RECHAZADOS (sin edge / beta disfrazada):** Candle Range Theory (gross≈0), Order-Block+PDH/PDL, Squeeze+MACD
  (era beta de momentum-stocks), Order Blocks/FVG/zonas de SMC, roster sobre PAXG (oro = beta), LITE/WDC (beta).
- **Datos:** descargados perps de oro (XAU ~6mo, PAXG ~15mo) al store.
- **Pendiente anotado (memoria):** 2ª oleada sBOS cripto (10 combos más) SI las S57–S64 confirman edge en vivo.

## TradFi (acciones) — 15 estrategias (perps de ACCIONES de Binance)
Sección **📈 TradFi** separada en el dashboard; mismas reglas/monto/apalancamiento que cripto; en paper, en sombra.
- **Titulares T2–T5** (NVDA/TSLA trend-following — Supertrend, Awesome Osc, Squeeze, ADX/DMI): validados con
  **años de la acción REAL** (Databento) → holdout IS/OOS + anti-beta. **Gated a sesión US regular** (09:30–16:00 ET).
- **Suplentes experimentales (role 0.5, session 24/7):**
  - **T1** ORB TSLA apertura volátil · **T6** NVDA ORB **pre-market agitado** (filtro invertido validado).
  - **T7–T11** S/R[LuxAlgo]+Supertrend (ST_flip + ruptura S/R-volumen): TSLA-L, AAPL-L, NVDA-L, MU-S, AMD-S.
    Selección por **anti-beta por (ticker,lado)** (solo pares con alpha real); corr ~0 vs T1–T6.
  - **T12–T15** SMC Swing BOS long-only: NVDA, TSLA, AAPL, MU (en cripto fue bidireccional → S57–S64).
- **Caveat clave:** T6–T15 se validaron sobre la acción real / extended-hours; corren sobre el **perp** (proxy
  fuera de sesión). El edge transfiere o no según el **paper vivo**. Nota de concentración: NVDA aparece en T2/T3/T4/T9/T12.
- **Rechazados (research):** LITE, WDC, AMD-L, MU-L y otros → beta o sin edge. El edge de timing en acciones es RARO.

**Arquitectura tradfi:** `tvbot/strategies_tradfi.py` (registro T1–T15) · `data.filter_us_session/in_us_session`
(DST-aware) · motor con `asset_class`/`session`/exit_mode `orb`+`atrstop` · `smc.py`/`sr_break_lux` para señales nuevas
· columna DB `asset_class` · toggle 🪙/📈 en el dashboard. **Reconcile cubre T2–T5 y T7–T15** (T1/T6 ORB = causalidad por construcción).

## Roster cripto: 64 estrategias (+ batch 8 SMC Swing BOS S57–S64)
Construido en 5 batches de research (todos validados OOS: IS<2025/OOS≥2025 + sensibilidad + correlación):

| Batch | Indicadores | Estrategias | Clase |
|-------|-------------|-------------|-------|
| Roster base | Supertrend, B-Xtrender, Trend Meter, HACOLT, Donchian/Ribbon, barridos | S1-S21 | trend-following |
| 1 | **Squeeze Momentum, Vortex** | S22-S29 | ruptura de volatilidad / direccional |
| 2 | **Bollinger %b** (reversión a la media) | S30 | reversión (motor `meanrev`) |
| 3 | **ADX/DMI, Squeeze-short** | S31-S36 | momentum direccional (edge grueso) |
| 4 | **Chaikin Money Flow, Force Index** | S37-S38 | volumen/flujo (ORDI long) |
| 5 | **KST, Awesome Oscillator, TSI** | S39-S44 | momentum-systems (monedas nuevas) |
| 6 | **Zero Lag Trend Signals** (AlgoAlpha) | S45-S48 | trend-pullback (monedas nuevas) |
| opt | challengers del optimizador (Squeeze/AO longs) | S49-S51 | corrige sesgo de antigüedad |
| 7 | **S/R High Volume Boxes** (ChartPrime) | S52-S56 | ruptura S/R + volumen (KVO y Turtle Soup descartados) |
| 8 | **Smart Money Concepts — Swing BOS** (LuxAlgo) | S57-S64 | ruptura de estructura swing (bidireccional; anti-beta+, OOS Sharpe 1.47) |

**Selección de roster (`roster_optimizer.py` + `metodologia-seleccion-roster`):** la redundancia y la
elección de estrategias se deciden por **correlación de PnL + contribución marginal al Sharpe**, NO por
antigüedad ni por nombre de indicador. El optimizador marca (no quita en fase paper) redundancias y
challengers mejores. Detectado: S2↔S1 redundante (corr 0.83, S2 marcada para observación).

Spec exacto y métricas: `CONSOLIDADO.md`. Veredictos de research: `indicadores_nuevos_/meanrev_/batch3_/batch4_/batch5_VEREDICTO.md`.

## Desempeño esperado (backtest, portafolio vol-parity 1/σ — `gen_summary.py`)
| Leverage | Mensual medio | MaxDD | Sharpe | Meses+ |
|----------|---------------|-------|--------|--------|
| 1× | +2.1% | −2.2% | 4.07 | 86% |
| 2× (arranque) | +4.1% | −4% | | |
| 3× | +6.2% | −7% | | |

~222 trades/mes · exp neto medio 114 bps/trade (neto de ganancias y pérdidas) · WR 42%.
**Caveat:** son números de backtest = techo. En vivo se conserva ~30-50% del edge y el DD vivo ~2× →
**expectativa realista: ~1-3% mensual a 2×**. Por eso esta fase de paper trading acumula evidencia antes del capital real.

## Arquitectura (ver ARQUITECTURA.md)
```
tvbot/  indicators.py (réplicas Pine, NO tocar sin re-validar; incl. sr_break_lux) · strategies.py (64 cripto) · strategies_tradfi.py (15) · ../smc.py (motor SMC)
        data.py (ccxt, velas cerradas) · engine.py (PaperEngine: salidas→entradas→equity)
        db.py (SQLite WAL) · orchestrator.py (bucle 15m/1h + circuit breaker) · api/app.py (FastAPI :8090)
deploy/ setup_vm.sh · deploy.sh · tvbot.service · tvbot-api.service (systemd, VM Oracle)
data/   tvbot.db (se crea solo) · logs/
```
Modos de salida: `atrstop` (SL 2×ATR + timeout 48h), `flip` (ST/TM contrario + SL 3×ATR), `meanrev`
(S30: vuelta a SMA20 + SL 3×ATR + timeout 24h). El bot usa ccxt en vivo (no depende del store de research).

## Dashboard web (puerto 8090)
- **Dashboard:** equity, PnL, WR, posiciones abiertas, gráficos por estrategia.
- **🚀 Producción (nuevo):** tracker de confirmación a nivel CARTERA — veredicto go-live del lote 1
  (Listo/Acumulando/Alerta), exp live vs backtest, ratio, maxDD vivo, estrategias confirmadas (X/8),
  reglas de gate visibles, y salud de stops/objetivos (MAE/MFE en R agregado).
- **Evaluación:** desempeño LIVE vs backtest por estrategia + veredicto + **gate de producción** +
  columnas **MAE(R)/MFE(R)** + descarga CSV.
- **Estrategias:** buscador + filtros (long/short, solo-con-trades) sobre las 56, **badge de trades
  (cerrados+abiertos)** por estrategia + marca ⚠ de redundancia; al seleccionar: indicadores, métricas e
  histórico completo (con MAE(R)/MFE(R) por trade).
- **Logs:** logs del sistema por rango de fecha + eventos recientes.

## Robustez operativa (pull-safe, no se pierden trades)
- Posiciones abiertas viven en la DB; al reiniciar se retoman y las salidas se **re-escanean desde la vela
  de entrada** (SL/timeout/flip perdidos durante una caída se detectan al volver). Fallback por reloj para
  trades más viejos que la ventana de datos.
- Migración de schema **idempotente** (`ALTER ADD COLUMN` en `db.init`) → un `git pull` que agrega columnas
  no rompe la DB en producción.
- Un trade abierto de una estrategia que ya no existe en el código (renombrada/quitada en un pull) **NO
  tumba el ciclo ni se pierde**: se mantiene abierto y se avisa para revisión manual (verificado en test).
- `deploy.sh` aborta el reinicio si fallan los imports (nunca reinicia con código roto).
- **Backup automático** de la DB 2×/día (`tvbot.backup`, systemd timer) con rotación — el track record
  no se pierde si la VM muere. **Watchdog** cada 10 min (`tvbot.watchdog`, timer): alerta si el bot no
  late (sin ciclo >40 min) o si saltó el circuit breaker. Alertas por **ntfy/Telegram** (`tvbot.notify`,
  configurables en `/opt/tvbot/.env`: `TVBOT_NTFY_URL`, `TVBOT_TG_TOKEN`/`TVBOT_TG_CHAT`).
- **Reconciliación señal viva vs backtest** (`reconcile.py`): verifica que el sN_entry (vivo) dispara en
  las mismas velas que el backtest. **Ahora cubre cripto (S1–S64) + tradfi (T2–T5, T7–T15)** → última corrida:
  **77 estrategias, 0 mismatches** (T1/T6 ORB son session-stateful → causalidad por construcción, no array).

## Desplegar en la VM
```bash
# primera vez: bash deploy/setup_vm.sh   (crea venv, instala, units systemd)
# actualizaciones:
git push                                  # desde local (79 estrategias: 64 cripto + 15 tradfi)
ssh <vm> 'bash /opt/tvbot/deploy/deploy.sh'   # git pull + pip + verificación de imports + restart
```
`deploy.sh` aborta si fallan los imports (no reinicia con código roto). Servicios: `tvbot` (bucle) y
`tvbot-api` (dashboard). Verificado local: `python -m tvbot --once` corre las 56; tests + seguridad de
reinicio OK. Las columnas nuevas de la DB se crean solas al reiniciar (migración idempotente).

## Contexto (proyecto unificado)
Este proyecto y **Oscilion** (otro bot, familia EMA/VWAP/ORB) acumulan datos de paper en paralelo; cuando
haya suficiente track record se elegirán los mejores candidatos para un proyecto unificado. Sin solape de
estrategias entre ambos (familias de indicadores disjuntas); sí solape de moneda (TRX/DOT/BTC), irrelevante
mientras ninguno opere capital real. Objetivo actual: **producir candidatos validados rápido**.

## Próximos pasos
1. **Desplegar la tanda operativa** (`git push` + `deploy.sh`): instala backup/watchdog timers; crear
   `/opt/tvbot/.env` con `TVBOT_NTFY_URL` (o Telegram) para recibir alertas.
2. **Acumular trades vivos** (~2-3 meses) y vigilar la pestaña 🚀 Producción hasta que la cartera confirme.
3. **Lote 1 a producción** con capital chico (1×) cuando se cumpla el gate de cartera; graduación rodante
   (alta frecuencia S2/S3/S7 primero).
4. Usar **MAE/MFE en vivo** para afinar stops/objetivos de las que confirmen; retirar las que el vivo condene.
5. Vigilar S22/S24 (ENA/WIF, historia corta), S37/S38 (ORDI, maxDD alto) y la redundancia S1/S2 (marcada).
6. **Metodología (P2): HECHO** → `deflated_sharpe.py` (Deflated Sharpe Ratio de Bailey-LdP, sin scipy).
   Corrige sesgo de selección (~185 pruebas) + no-normalidad. Veredicto: PSR(0)=100% y DSR=100% aun
   asumiendo N=1000 pruebas → el Sharpe de cartera NO es artefacto de muestreo/selección. La mejor
   estrategia SUELTA (S22) apenas roza 97.7% → el edge vive en la combinación (√N), no en ninguna
   individual. Límite honesto: el DSR no ve el sobreajuste a este histórico → el juez sigue siendo el paper.
7. **Unificado (P3):** schema de trade estándar con Oscilion + correlación cruzada entre proyectos.
8. Reconciliación **automatizada (HECHO)**: `git pre-push hook` (`hooks/pre-push`, activado con
   `git config core.hooksPath hooks`) corre `reconcile.py` SOLO si el push toca la lógica de señal
   (`indicators.py`/`strategies.py`/cadena de backtest) y **bloquea el push** si hay mismatches
   (override `--no-verify`). Es local porque el store de parquets no está en la VM. Pushes que no tocan
   señal no se ralentizan. `reconcile.py` ahora devuelve exit-code ≠0 en mismatch.

> **Hecho hoy:** tracker de cartera + gates + captura enriquecida + backup/watchdog/alertas + reconciliación.
> El cuello de botella ahora es TIEMPO de acumular trades — NO añadir más estrategias (diluiría).

> **Importante:** los nombres de las estrategias son irrelevantes — el roster vivo se decide por resultados
> (gates objetivos). Cada trade guarda datos ricos (contexto + MAE/MFE) para esas decisiones.
