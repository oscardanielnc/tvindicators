# Estado del proyecto — tvindicators
**Actualizado:** 2026-06-15 · Fase: **paper trading (listo para desplegar en VM)**

## Resumen en una línea
Bot de paper trading con **56 estrategias validadas OOS** sobre Binance perps (TF 1h/15m), motor con
paridad exacta al backtest, API + dashboard web, y track record vivo que decidirá el capital real.

## Roster: 56 estrategias (7 titulares + 49 suplentes · 26 long / 30 short)
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
tvbot/  indicators.py (réplicas Pine, NO tocar sin re-validar) · strategies.py (44 + BACKTEST_REF)
        data.py (ccxt, velas cerradas) · engine.py (PaperEngine: salidas→entradas→equity)
        db.py (SQLite WAL) · orchestrator.py (bucle 15m/1h + circuit breaker) · api/app.py (FastAPI :8090)
deploy/ setup_vm.sh · deploy.sh · tvbot.service · tvbot-api.service (systemd, VM Oracle)
data/   tvbot.db (se crea solo) · logs/
```
Modos de salida: `atrstop` (SL 2×ATR + timeout 48h), `flip` (ST/TM contrario + SL 3×ATR), `meanrev`
(S30: vuelta a SMA20 + SL 3×ATR + timeout 24h). El bot usa ccxt en vivo (no depende del store de research).

## Dashboard web (puerto 8090)
- **Dashboard:** equity, PnL, WR, posiciones abiertas, gráficos por estrategia.
- **Evaluación:** desempeño LIVE vs backtest + veredicto (Confirmada/En línea/Vigilar/Quitar) + descarga CSV.
- **Estrategias:** buscador + filtros (long/short, solo-con-trades) sobre las 44, con **badge numérico de
  trades (cerrados+abiertos)** por estrategia; al seleccionar: indicadores, métricas e histórico completo.
- **Logs:** logs del sistema por rango de fecha + eventos recientes.

## Desplegar en la VM
```bash
# primera vez: bash deploy/setup_vm.sh   (crea venv, instala, units systemd)
# actualizaciones:
git push                                  # desde local (44 estrategias listas)
ssh <vm> 'bash /opt/tvbot/deploy/deploy.sh'   # git pull + pip + verificación de imports + restart
```
`deploy.sh` aborta si fallan los imports (no reinicia con código roto). Servicios: `tvbot` (bucle) y
`tvbot-api` (dashboard). Verificado local: `python -m tvbot --once` corre las 44; tests de salidas OK.

## Contexto (proyecto unificado)
Este proyecto y **Oscilion** (otro bot, familia EMA/VWAP/ORB) acumulan datos de paper en paralelo; cuando
haya suficiente track record se elegirán los mejores candidatos para un proyecto unificado. Sin solape de
estrategias entre ambos (familias de indicadores disjuntas); sí solape de moneda (TRX/DOT/BTC), irrelevante
mientras ninguno opere capital real. Objetivo actual: **producir candidatos validados rápido**.

## Pendientes / ideas
- Pushear y desplegar en la VM (commits locales listos).
- Acumular ≥30 trades/estrategia para el gate de evaluación en vivo.
- Vigilar S22/S24 (ENA/WIF, historia corta) y S37/S38 (ORDI, maxDD 1× alto).
- Batch 6 posible: filtro de régimen (Choppiness/ADX) para *subir* el edge del roster existente, o multi-TF.
