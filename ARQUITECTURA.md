# tvbot — Arquitectura (Fase 2: paper trading)

## Qué es
Bot que opera en **simulado** las 9 estrategias validadas (ver CONSOLIDADO.md) con $1,000
virtuales, margen 10% fijo ($100) y apalancamiento 5× fijo por trade. Genera el track
record vivo que decidirá pesos/apalancamiento reales.

## Estructura
```
tvindicators/
├── config.py                  # capital, leverage, costos, puertos (env-overridable)
├── requirements.txt
├── tvbot/
│   ├── indicators.py          # réplicas Pine EXACTAS del backtest (no tocar sin re-validar)
│   ├── strategies.py          # las 9 estrategias (entry/exit declarativos)
│   ├── data.py                # ccxt binanceusdm, solo velas CERRADAS, funding history
│   ├── engine.py              # PaperEngine: exits → entries → equity snapshot
│   ├── db.py                  # SQLite WAL: trades, equity_snapshots, signals, events
│   ├── orchestrator.py        # bucle cada 15m (+20s), 1h en cada hora, circuit breaker
│   ├── logging_setup.py
│   ├── __main__.py            # python -m tvbot [--once]
│   └── api/app.py             # FastAPI puerto 8090
├── deploy/tvbot.service       # systemd (VM Oracle)
├── deploy/tvbot-api.service
└── data/tvbot.db              # se crea solo
```

## Cómo correr
```
python -m tvbot --once     # un ciclo (smoke test)
python -m tvbot            # bucle continuo
python -m tvbot.api        # API en :8090
```

## Paridad con el backtest (decisiones de diseño)
1. Señal evaluada SOLO en la última vela CERRADA (se descarta la vela en curso).
2. Entrada = open de la vela en curso al detectar (≈ open de i+1 del backtest), fee maker.
3. atrstop: SL = entrada ∓ 2×ATR14(vela señal), evaluado contra low/high de velas cerradas
   del MISMO timeframe (no intra-vela) → exactamente como el backtest. Salida SL paga
   taker+slippage; timeout 48h y flip pagan maker.
4. Funding real por trade vía fetch_funding_rate_history al cierre (long paga, short cobra).
5. 1 posición por estrategia a la vez (entry_skipped se registra en signals para auditoría).
6. Restart-safe: posiciones abiertas viven en la DB; al reiniciar se retoman.

## API (para el frontend)
- GET /api/health             — latido
- GET /api/status             — equity actual, posiciones abiertas, W/L, PnL total
- GET /api/equity?limit=      — curva de equity (snapshots cada ciclo)
- GET /api/summary            — por estrategia: #trades, wins, PnL total (gráfico de barras)
- GET /api/strategies         — catálogo de las 9
- GET /api/trades?strategy_id=&status=&limit= — histórico completo por estrategia
- GET /api/trades/{id}        — detalle de un trade
- GET /api/events             — log operativo

Campos por trade: fechas señal/entrada/salida, moneda, long/short, monto base, leverage,
notional, entry/exit px, stop, timeout, razón de salida (SL/timeout/flip), PnL USD, fees,
funding, %ret con y sin apalancamiento, ATR de entrada, barras en posición.

## Riesgo conocido a 5×
Stop de 2×ATR en 1h ≈ movimientos de 2-5% → pérdida típica por SL ≈ 10-25% del margen
($10-25 de $100). Liquidación a 5× requeriría ~19% en contra: improbable antes del stop,
pero gaps extremos existen — en real se usará isolated margin.
