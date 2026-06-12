"""Motor de paper trading: evalua senales en velas cerradas y gestiona posiciones virtuales.

Paridad con el backtest validado:
- Senal al cierre de vela i -> entrada al open de la vela i+1 (= vela en curso al detectar).
- atrstop: SL = entrada -/+ 2*ATR14(vela de senal), chequeado contra low/high de cada
  vela cerrada (salida a precio de stop, costo taker+slippage). Timeout 48h -> salida
  al open actual (costo maker).
- flip: salida cuando el Supertrend gira en contra (costo maker).
- Funding real acumulado entre entrada y salida (lo paga el long, lo cobra el short).
"""
import json
from datetime import datetime, timedelta

import config
from . import data, db
from .indicators import atr14
from .strategies import STRATEGIES, BY_ID


def _now():
    return datetime.now(config.LIMA_TZ)      # hora de Lima en todo el sistema


def _iso(dt):
    return dt.isoformat(timespec="seconds")


class PaperEngine:
    def __init__(self):
        db.init()
        self.capital0 = config.CAPITAL_INICIAL

    # ---------- ciclo principal ----------
    def run_cycle(self, due_tfs):
        """due_tfs: lista de timeframes cuya vela acaba de cerrar (p.ej. ['15m','1h'])."""
        needed = {}
        for s in STRATEGIES:
            if s.tf in due_tfs:
                needed.setdefault((s.symbol, s.tf), None)
        for trade in db.open_trades():
            if trade["tf"] in due_tfs:
                needed.setdefault((trade["symbol"], trade["tf"]), None)

        market = {}
        for (symbol, tf) in needed:
            df, live_open = data.retry(lambda s=symbol, t=tf: data.fetch_bars(s, t))
            market[(symbol, tf)] = (df, live_open)

        self._manage_exits(market, due_tfs)
        self._manage_entries(market, due_tfs)
        self._snapshot(market)

    # ---------- salidas ----------
    def _manage_exits(self, market, due_tfs):
        for tr in db.open_trades():
            if tr["tf"] not in due_tfs or (tr["symbol"], tr["tf"]) not in market:
                continue
            df, live_open = market[(tr["symbol"], tr["tf"])]
            last = df.iloc[-1]
            entry_t = datetime.fromisoformat(tr["t_entry"])
            if df.index[-1].to_pydatetime() <= entry_t:
                continue            # la vela de entrada aun no cierra
            side = 1 if tr["side"] == "long" else -1
            strat = BY_ID[tr["strategy_id"]]
            exit_px = reason = None
            cost_out = config.MAKER_FEE

            if strat.exit_mode == "atrstop":
                stop = tr["stop_px"]
                hit = last["low"] <= stop if side > 0 else last["high"] >= stop
                if hit:
                    exit_px = min(last["open"], stop) if side > 0 else max(last["open"], stop)
                    reason = "SL"
                    cost_out = config.TAKER_FEE + config.SLIPPAGE
                elif _now() >= datetime.fromisoformat(tr["timeout_at"]):
                    exit_px, reason = live_open, "timeout"
            else:                                       # flip
                if strat.exit_signal(df):
                    exit_px, reason = live_open, "flip"

            if exit_px is not None:
                self._close(tr, float(exit_px), reason, cost_out, df)

    def _close(self, tr, exit_px, reason, cost_out, df):
        side = 1 if tr["side"] == "long" else -1
        notional, margin = tr["notional"], tr["base_amount"]
        gross_pct = side * (exit_px / tr["entry_px"] - 1)
        fees_usd = (config.MAKER_FEE + cost_out) * notional
        entry_ms = datetime.fromisoformat(tr["t_entry"]).timestamp() * 1000
        fund_sum = data.funding_since(tr["symbol"], entry_ms, _now().timestamp() * 1000)
        funding_usd = -side * fund_sum * notional        # long paga si funding>0; short cobra
        pnl = gross_pct * notional - fees_usd + funding_usd
        ret_nolev = pnl / notional
        ret_lev = pnl / margin
        bars_held = int((df.index[-1].to_pydatetime()
                         - datetime.fromisoformat(tr["t_entry"])).total_seconds()
                        // (900 if tr["tf"] == "15m" else 3600))
        db.close_trade(tr["id"], t_exit=db.utcnow(), exit_px=exit_px, exit_reason=reason,
                       pnl_usd=round(pnl, 4), fees_usd=round(fees_usd, 4),
                       funding_usd=round(funding_usd, 4),
                       ret_pct_lev=round(ret_lev * 100, 4),
                       ret_pct_nolev=round(ret_nolev * 100, 4), bars_held=bars_held)
        db.log_signal(tr["strategy_id"], tr["symbol"], "exit",
                      {"reason": reason, "px": exit_px, "pnl": round(pnl, 2)})
        db.log_event("info", "trade",
                     f"{tr['strategy_id']} cierra {tr['side']} {tr['symbol']} @ {exit_px} "
                     f"({reason}) PnL ${pnl:+.2f}")

    # ---------- entradas ----------
    def _manage_entries(self, market, due_tfs):
        open_by_strat = {t["strategy_id"] for t in db.open_trades()}
        for s in STRATEGIES:
            if s.tf not in due_tfs or (s.symbol, s.tf) not in market:
                continue
            df, live_open = market[(s.symbol, s.tf)]
            try:
                signal = s.entry_signal(df)
            except Exception as e:
                db.log_event("error", "signal", f"{s.sid} error evaluando senal: {e}")
                continue
            if not signal:
                continue
            if s.sid in open_by_strat:
                db.log_signal(s.sid, s.symbol, "entry_skipped", {"motivo": "posicion abierta"})
                continue
            self._open(s, df, float(live_open))

    def _open(self, s, df, entry_px):
        margin = self.capital0 * config.MARGIN_PCT          # 10% fijo de $1000
        notional = margin * config.LEVERAGE                  # 5x
        qty = notional / entry_px
        atr = float(atr14(df).iloc[-1])
        stop_px = entry_px - (1 if s.side > 0 else -1) * config.ATR_MULT * atr \
            if s.exit_mode == "atrstop" else None
        timeout_at = _iso(_now() + timedelta(hours=config.TIMEOUT_HOURS)) \
            if s.exit_mode == "atrstop" else None
        tid = db.insert_trade(
            strategy_id=s.sid, strategy_name=s.name, symbol=s.symbol, tf=s.tf,
            side="long" if s.side > 0 else "short", status="open",
            t_signal=_iso(df.index[-1].to_pydatetime().astimezone(config.LIMA_TZ)),
            t_entry=db.utcnow(),
            entry_px=entry_px, base_amount=margin, leverage=config.LEVERAGE,
            notional=notional, qty=qty, stop_px=stop_px, timeout_at=timeout_at,
            atr_entry=atr, signal_meta=json.dumps({"exit_mode": s.exit_mode}))
        db.log_signal(s.sid, s.symbol, "entry", {"px": entry_px, "trade_id": tid})
        db.log_event("info", "trade",
                     f"{s.sid} abre {'long' if s.side > 0 else 'short'} {s.symbol} @ {entry_px} "
                     f"(margen ${margin:.0f} x{config.LEVERAGE:.0f})")

    # ---------- equity ----------
    def _snapshot(self, market):
        realized = db.realized_pnl()
        unreal, detail = 0.0, {}
        for tr in db.open_trades():
            key = (tr["symbol"], tr["tf"])
            px = market[key][1] if key in market else None
            if px is None:
                continue
            side = 1 if tr["side"] == "long" else -1
            u = side * (px / tr["entry_px"] - 1) * tr["notional"]
            unreal += u
            detail[tr["strategy_id"]] = round(u, 2)
        equity = self.capital0 + realized + unreal
        db.snapshot_equity(round(equity, 2), round(realized, 2), round(unreal, 2),
                           len(detail), detail)
