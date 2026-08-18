# tvbot — Systematic Trading Research & Paper-Trading Platform

An end-to-end quantitative trading system: a research pipeline that discovers and statistically
validates trading strategies, and a production service that runs the surviving strategies live
against real market data — instrumented well enough to prove itself wrong.

**It did prove itself wrong.** After 52 days and 272 live trades, the backtested edge failed to
transfer (−14.7 bps/trade live vs +105 bps backtested, t = −6.9). That negative result — and the
instrumentation built to establish it beyond doubt — is the point of this repository.

```
Python 3.11 · FastAPI · SQLite (WAL) · pandas / NumPy · ccxt · systemd · Oracle Cloud
```

| | |
|---|---|
| **Status** | Live in production, 90+ days continuous uptime |
| **Scale** | ~15,200 LOC · 79 strategies · 32 indicator primitives · 15 REST endpoints |
| **Deployment** | Oracle Cloud VM · 6 systemd units · automated deploy with rollback gate |
| **Capital at risk** | $0 — paper trading by design (see *Why paper trading*) |

---

## Table of contents

- [The problem](#the-problem)
- [Architecture](#architecture)
- [Engineering decisions that mattered](#engineering-decisions-that-mattered)
- [Statistical validation](#statistical-validation)
- [Production operations](#production-operations)
- [Results — the honest version](#results--the-honest-version)
- [Running it](#running-it)
- [Repository layout](#repository-layout)
- [What I'd do differently](#what-id-do-differently)

---

## The problem

Backtested trading strategies almost always look profitable and almost always fail live. The two
causes are **overfitting** (you tested 185 ideas and kept the luckiest) and **implementation drift**
(the live system doesn't do what the backtest did).

This project attacks both as *engineering* problems:

1. **Overfitting** → a validation pipeline with out-of-sample gates, anti-beta controls, and the
   Deflated Sharpe Ratio to price in selection bias across every hypothesis tested.
2. **Drift** → a live engine built for bit-level parity with the backtest, plus a reconciliation
   harness that continuously proves the two agree.

The deliverable isn't a profitable bot. It's a machine that produces **trustworthy evidence** about
whether an edge exists.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
   Binance USD-M ──────▶│  data.py — ccxt, closed candles only,    │
   (REST, public)       │  funding-rate history, US-session filter │
                        └────────────────────┬─────────────────────┘
                                             │ OHLCV DataFrames
                        ┌────────────────────▼─────────────────────┐
                        │  indicators.py — 32 primitives, exact    │
                        │  ports of the Pine Script used in        │
                        │  research (Supertrend, ADX/DMI, Squeeze, │
                        │  Vortex, KST, TSI, HACOLT, SMC/BOS, …)   │
                        └────────────────────┬─────────────────────┘
                                             │
                        ┌────────────────────▼─────────────────────┐
                        │  strategies.py (64) + strategies_tradfi  │
                        │  .py (15) — declarative entry/exit specs │
                        └────────────────────┬─────────────────────┘
                                             │
      ┌──────────────────────────────────────▼──────────────────────────────────┐
      │  engine.py — PaperEngine                                                │
      │  exits first → entries → equity snapshot   (order is load-bearing)      │
      │  ├─ shadow.py  counterfactual exit replay (never touches execution)     │
      │  └─ theses.py  aggregates 79 strategies into 6 economic hypotheses      │
      └──────────────────────────────────────┬──────────────────────────────────┘
                                             │
                        ┌────────────────────▼─────────────────────┐
                        │  db.py — SQLite WAL                      │
                        │  trades · equity_snapshots · signals ·   │
                        │  events                                  │
                        └────────┬───────────────────────┬─────────┘
                                 │                       │
              ┌──────────────────▼──────┐   ┌────────────▼────────────────┐
              │ orchestrator.py         │   │ api/app.py — FastAPI        │
              │ 15m loop (+20s offset)  │   │ 15 endpoints + dashboard    │
              │ circuit breaker         │   │ (single-page, Chart.js)     │
              └─────────────────────────┘   └─────────────────────────────┘
```

Two independent systemd services share the SQLite file: the trading loop (`tvbot`) writes, the API
(`tvbot-api`) reads. WAL mode makes concurrent reads safe without blocking the writer.

---

## Engineering decisions that mattered

### Backtest/live parity is a hard constraint, not an aspiration

The engine mirrors the backtest exactly, and the non-obvious parts are the ones that matter:

- **Signals fire on closed candles only.** A signal at the close of bar *i* enters at the open of
  bar *i+1*. Reading an in-progress candle is the single most common way a backtest lies to you.
- **Intra-bar exit detection.** Stops are checked against the low/high of *every* bar since entry,
  not just the latest one — an early bug only detected stops on the most recent candle, which
  silently inflated returns. `tests/test_exits.py` exists specifically to prevent its return.
- **Real funding costs** are fetched per-trade from the exchange's funding history and applied by
  side (longs pay, shorts collect), rather than assumed as a constant.
- **Maker vs taker fees** are applied per exit type: stop-outs pay taker + slippage, timeouts and
  signal flips pay maker.

### A reconciliation harness that proves parity continuously

`reconcile.py` replays live-recorded signals through the backtest code path and diffs the results.
When the live P&L went negative, this is what ruled out execution bugs as the cause: **0 mismatches**
across the full trade history. Without it, "the strategy is bad" and "the code is broken" would have
been indistinguishable.

### Shadow logging — counterfactuals without touching execution

`shadow.py` replays each closed trade's exact candles under alternative exit rules (stops at
0.5/0.75/1.5R, take-profits at 1/1.5/2/3R, breakeven, trailing) and records what *would* have
happened.

This makes exit-rule tuning an out-of-sample decision instead of a retrofit — the usual way people
overfit their way out of a losing system. Critically, it is a pure observer: it writes to its own
table and cannot influence a live position. `tests/test_shadow.py` asserts the `base` variant
reproduces actual returns (median deviation +0.0 bps, 0/168 trades deviating >25 bps) *and* that
execution is unaffected.

### Flat sizing to make P&L a clean estimator

Originally each trade was sized by volatility-derived leverage. The audit found crypto-shorts had
earned **+$88 at 0.0 bps/trade** — every dollar came from position sizing, none from signal quality.

Switching to constant notional (`SIZING_MODE='flat'`) makes each trade weigh equally, so dollar P&L
becomes an unbiased estimate of edge. Risk-based sizing remains behind the flag, to be re-enabled
per-strategy only after a thesis is confirmed profitable. **Measure first, optimize sizing second.**

### Aggregating 79 strategies into 6 hypotheses

Testing 79 strategies against a significance threshold guarantees false positives. `theses.py`
groups them into 6 economic bets (*stock ORB*, *alt shorts 1h*, *crypto longs*, …) and gates on
t-statistic and 95% CI at the thesis level. This cuts the multiple-comparisons problem from 79
hypotheses to 6 and reflects how the bets actually correlate.

It also produces the sharpest finding in the project — the ability to distinguish *"not enough data
yet"* from *"this edge is too thin to ever be confirmable."* The alt-shorts thesis showed +0.4 bps
with t = 0.02: reaching significance would require **~2.1 million trades**. That thesis is dead, and
no amount of patience fixes it.

### Operational resilience

- **Circuit breaker** — consecutive failures pause the loop rather than hammering the exchange.
- **Idempotent cycles** — `python -m tvbot --once` runs a single cycle for smoke tests; re-running a
  cycle cannot double-open a position.
- **Timezone discipline** — the entire system (DB, logs, API, scheduling) is pinned to
  `America/Lima` (UTC−5, no DST). Mixed timezones are a recurring source of off-by-one-bar bugs.
- **Env-overridable config** — every parameter in `config.py` reads from the environment, so the VM
  is configured without touching code.

---

## Statistical validation

The research pipeline (`sweep*.py`, `poc_*.py`, `valida_*.py`) applies escalating tests. Ideas are
rejected far more often than accepted — see the `*_VEREDICTO.md` files, which document failures as
carefully as successes.

| Control | Purpose |
|---|---|
| **In-sample / out-of-sample split** | IS < 2025, OOS ≥ 2025. Must survive both. |
| **Anti-beta, per symbol** | Does the strategy beat buy-and-hold *on that instrument*? Killed several apparent winners that were just long exposure to a rising asset. |
| **Correlation-based roster selection** | `roster_optimizer.py` selects on P&L correlation and marginal Sharpe contribution, not on backtest rank — avoids stacking twelve versions of the same bet. |
| **Deflated Sharpe Ratio** | `deflated_sharpe.py` — Bailey & López de Prado (2014). Corrects the headline Sharpe for sample length, skew/kurtosis, *and* selection across all ~185 candidates tested. |
| **Risk of ruin** | `riesgo_ruina.py` — Monte Carlo over the leverage policy. |

**On the Deflated Sharpe result:** the portfolio's 4.07 backtested Sharpe was chosen after testing
~185 candidates. Under the null hypothesis, the best of 185 tries looks excellent by construction.
The DSR quantifies exactly that, and the module's docstring states plainly that *no* backtest
segment is truly clean, because OOS was used as a selection gate. The only honest holdout is live
paper trading — which is why the system exists.

---

## Production operations

Deployed on an Oracle Cloud VM (`/opt/tvbot`), 90+ days continuous uptime.

**6 systemd units:**

| Unit | Role |
|---|---|
| `tvbot.service` | Trading loop, `Restart=always` |
| `tvbot-api.service` | FastAPI dashboard on :8090 |
| `tvbot-backup.{service,timer}` | DB snapshot twice daily |
| `tvbot-watchdog.{service,timer}` | Liveness check every ~10 min |

**Watchdog** treats the latest `equity_snapshot` as a heartbeat. No snapshot in 40 minutes means the
loop, service, or VM is down and trades are being missed — it alerts via ntfy and/or Telegram
(`notify.py`, stdlib `urllib` only, no-op when unconfigured).

**Deploy** (`deploy/deploy.sh`) is a single idempotent command with a safety gate:

```bash
git pull --ff-only          # SSH deploy key via sudo -H
pip install -r requirements.txt
python -c "import config; from tvbot import engine, orchestrator, ..."   # ← import check
                                                                        #   fails ⇒ NO restart
systemctl restart tvbot tvbot-api
```

A broken commit fails the import verification and the running services are left untouched, rather
than restarting into a crash loop.

---

## Results — the honest version

**52 days · 272 closed trades · equity $1,000 → $926 (−7.4%) · max drawdown −28.4%**

| Metric | Live | Backtest |
|---|---|---|
| Expectancy | **−14.7 bps/trade** | +105 bps/trade |
| Win rate | 37% | — |
| Profit factor | 0.90 | — |
| Strategies confirmed | **0 / 62** | — |

The statistically careful statement: t vs 0 is −0.85, so **you cannot prove the system loses money**.
But t vs +105 bps is **−6.9** — you *can* decisively reject that the backtested edge survived
contact with live markets. This is not variance. It is a transfer failure.

The instrumentation ruled out the convenient explanations:

- **Not execution** — reconciliation reports 0 mismatches.
- **Not costs** — fees ran 6 bps of notional; gross P&L was negative too (−$34).
- **Not regime** — trades tagged with favorable regime performed *worse* (−36 vs +22 bps), which is
  a finding about the regime filter's predictive power, not a bug.
- **Concentration** — remove the 5 best trades and P&L is −$244; remove the 5 worst and it's +$10.
  272 trades, ~10 of which determine the outcome.

One thesis remains alive: **stock ORB** (opening-range breakout on equity perpetuals), currently
+99.9 bps/trade over 13 trades, t = 1.79, needing ~17 trades to reach significance. It is being
collected, not traded with real money.

**Why this section exists.** It would be trivial to publish the 4.07 Sharpe backtest and stop there.
The reason the system logs counterfactuals, reconciles against the backtest, aggregates to theses,
and deflates its own Sharpe is so that when the answer is *"your edge isn't real,"* it arrives with
enough evidence to be believed. Building systems that can falsify your own hypothesis — and then
reporting it — is the job.

---

## Running it

```bash
git clone https://github.com/oscardanielnc/tvindicators.git
cd tvindicators
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m tvbot --once      # single cycle, smoke test
python -m tvbot             # continuous loop
python -m tvbot.api         # dashboard at http://localhost:8090
```

No API keys or exchange credentials are required — the system reads public market data only and
never places real orders.

**Tests** (self-asserting scenario suites, no network):

```bash
python -m tests.test_exits    # 5 scenarios: stop-loss, flip, timeout, short SL, safety stop
python -m tests.test_shadow   # 5 scenarios: fidelity, tighter stops, TP/breakeven, isolation
```

**Configuration** — all via environment variables (`config.py`): `TVBOT_CAPITAL`,
`TVBOT_SIZING_MODE`, `TVBOT_DB`, `TVBOT_NTFY_URL`, `TVBOT_TG_TOKEN`, …

---

## Repository layout

```
tvbot/                    Production service
├── indicators.py         32 indicator primitives (exact Pine Script ports)
├── strategies.py         64 crypto strategies, declarative specs
├── strategies_tradfi.py  15 equity-perpetual strategies (US session gating)
├── engine.py             PaperEngine — exits, entries, equity snapshots
├── shadow.py             Counterfactual exit replay
├── theses.py             Thesis-level aggregation and gating
├── data.py               ccxt feed, closed candles, funding history
├── db.py                 SQLite WAL schema and access
├── orchestrator.py       Main loop, circuit breaker
├── watchdog.py           Heartbeat monitor
├── backup.py / notify.py Backups, ntfy/Telegram alerts
└── api/app.py            FastAPI — 15 endpoints + single-page dashboard

deploy/                   systemd units + deploy.sh + VM provisioning
tests/                    Synthetic scenario suites
design/                   Design system (see below)

sweep*.py, poc_*.py       Research: parameter sweeps, proofs of concept
valida_*.py               Validation gates (IS/OOS, anti-beta, holdout)
deflated_sharpe.py        Deflated / Probabilistic Sharpe Ratio
roster_optimizer.py       Correlation-based portfolio selection
riesgo_ruina.py           Monte Carlo risk of ruin
*_VEREDICTO.md            Written verdicts — including the rejections
tradfi/                   Equity-perpetual research (ORB, intraday patterns)
```

### Design system

The dashboard follows **Luminous**, a design system defined in `design/luminous/` — tokens
(surfaces, semantic long/short colors, 2/4/8/12px radii), Hanken Grotesk for UI, JetBrains Mono
with tabular numerals for all figures. `design/stitch/README.md` documents the pipeline used to
produce and version it.

---

## What I'd do differently

- **Paper-trade before building the full roster.** 79 strategies were validated offline before a
  single live trade. Running the top 5 live for 60 days first would have surfaced the transfer
  failure months earlier and much more cheaply.
- **Make tests pytest-discoverable.** The suites are thorough but named as scripts, so they don't
  collect under `pytest` and can't gate CI.
- **Add CI.** There is no GitHub Actions workflow; the import check in `deploy.sh` is the only
  automated gate.
- **Type hints and a linter.** The codebase is untyped; `mypy` and `ruff` would pay for themselves
  in a project this size.
- **Postgres over SQLite** if a second writer is ever needed. WAL handles the current
  one-writer/one-reader split well, but it's a ceiling.

---

## Why paper trading

The system trades simulated capital deliberately. The premise is that a strategy earns real money
only after it demonstrates edge on a clean, forward-looking holdout — and by the project's own gate
(≥80 trades per thesis, t > 2.0, PF > 1.15), **none has**. Deploying capital before that point would
be substituting hope for evidence.

---

*Documentation in `ARQUITECTURA.md`, `METODOLOGIA_PRODUCCION.md`, `VALIDACION_Y_PRODUCCION.md` and
`ESTADO_PROYECTO.md` is written in Spanish.*
