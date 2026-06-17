# Estado del proyecto — tvindicators
**Actualizado:** 2026-06-16 (sesión "indicadores populares de TradingView") · Fase: **DESPLEGADO en producción (paper trading en VM)** ✅

> **Cripto desplegado 2026-06-15; TradFi añadido 2026-06-16; roster ampliado el mismo día con indicadores
> populares validados.** Roster actual: **64 estrategias cripto + 15 tradfi = 79** corriendo en sombra en la
> VM; backup/watchdog/alertas activos; reconciliación ahora cubre cripto + tradfi (77 reconciliadas, 0 mismatches).
> Código en `origin/main` (commit más nuevo pendiente de push: T12–T15 + reconcile tradfi).
> Fase: **esperar y vigilar** hasta que la cartera confirme el backtest. VM: `ssh <vm> 'bash /opt/tvbot/deploy/deploy.sh'`.

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
