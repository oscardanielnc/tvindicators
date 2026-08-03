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

import pandas as pd

import config
from . import data, db, shadow
from . import indicators as I
from .indicators import atr14
from .strategies import STRATEGIES, BY_ID, _btc_bull
from .strategies_tradfi import STRATEGIES_TRADFI, BY_ID_TRADFI

# cripto + tradfi (perps de acciones). El feed y el motor son comunes; lo único distinto de tradfi
# es la sesión ('us' -> solo barras de sesión US regular) y el exit_mode 'orb'.
_ALL = STRATEGIES + STRATEGIES_TRADFI
_BY_ID = {**BY_ID, **BY_ID_TRADFI}
_TF_S = {"15m": 900, "30m": 1800, "1h": 3600}


def _view(strat, df):
    """Vista del df que ve la estrategia: titulares 'us' solo ven barras de sesión US regular."""
    return data.filter_us_session(df) if getattr(strat, "session", "24/7") == "us" else df


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
        session_open = data.in_us_session()       # gating de titulares 'us' (acciones)
        for s in _ALL:
            if s.tf in due_tfs and not (getattr(s, "session", "24/7") == "us" and not session_open):
                needed.setdefault((s.symbol, s.tf), None)
        for trade in db.open_trades():
            if trade["tf"] in due_tfs:            # las SALIDAS siempre se gestionan (la vista filtra a sesión;
                needed.setdefault((trade["symbol"], trade["tf"]), None)  # así el ORB cierra en el ciclo de las 16:00)

        market = {}
        for (symbol, tf) in needed:
            try:
                df, live_open = data.retry(lambda s=symbol, t=tf: data.fetch_bars(s, t))
                market[(symbol, tf)] = (df, live_open)
            except Exception as e:
                # un simbolo con datos malos NO tumba el ciclo de los demas;
                # sus stops se re-evaluan en el proximo ciclo (el motor revisa
                # TODAS las velas desde la entrada, nada se pierde)
                db.log_event("warn", "data",
                             f"sin datos frescos {symbol} {tf} — saltado este ciclo: {e}")
        if needed and not market:
            raise RuntimeError("sin datos de mercado para ningun simbolo (¿red caida?)")

        self._manage_exits(market, due_tfs)
        self._manage_entries(market, due_tfs)
        self._snapshot(market)

    # ---------- salidas ----------
    def _manage_exits(self, market, due_tfs):
        """Recorre TODAS las velas cerradas desde la entrada (no solo la ultima).
        Asi, si el bot estuvo caido o salto ciclos, ningun SL/flip/timeout se pierde:
        se detecta en la primera vela donde debio dispararse (paridad con backtest)."""
        for tr in db.open_trades():
            if tr["tf"] not in due_tfs or (tr["symbol"], tr["tf"]) not in market:
                continue
            raw_df, live_open = market[(tr["symbol"], tr["tf"])]
            strat = _BY_ID.get(tr["strategy_id"])
            if strat is None:
                # estrategia ya no existe en el código (renombrada/quitada en un pull):
                # NO se pierde el trade — se deja abierto y se avisa para revisión manual.
                db.log_event("warn", "exits",
                             f"trade {tr['id']} de estrategia desconocida {tr['strategy_id']} "
                             f"— se mantiene abierto para revisión (no se pierde)")
                continue
            df = _view(strat, raw_df)             # titulares 'us' ven solo barras de sesión US
            side = 1 if tr["side"] == "long" else -1
            tf_s = _TF_S[tr["tf"]]
            entry_t = datetime.fromisoformat(tr["t_entry"])
            # vela de entrada = la que contiene t_entry (alineada al timeframe)
            entry_bar_start = int(entry_t.timestamp() // tf_s) * tf_s
            # epoch en segundos, robusto ante la unidad interna del indice (ns/ms)
            starts = ((df.index - pd.Timestamp("1970-01-01", tz="UTC"))
                      // pd.Timedelta("1s")).to_numpy()
            i0 = int(starts.searchsorted(entry_bar_start))
            if i0 >= len(df):
                continue                      # la vela de entrada aun no cierra
            op, hi, lo, cl = (df["open"].values, df["high"].values,
                              df["low"].values, df["close"].values)
            timeout_h = strat.timeout_h or config.TIMEOUT_HOURS
            to_bars = timeout_h * 3600 // tf_s
            # 'flip' y 'meanrev' usan array de salida; 'atrstop' y 'meanrev' tienen timeout
            flip = strat.exit_array(df) if strat.exit_mode in ("flip", "meanrev") else None
            has_timeout = strat.exit_mode in ("atrstop", "meanrev")
            # 'orb' (acciones): cierre en la última vela de la sesión (15m->15:45, 30m->15:30 ET)
            if strat.exit_mode == "orb":
                et = df.index.tz_convert(data._ET)
                et_mod = (et.hour * 60 + et.minute).to_numpy()
                close_slot = 16 * 60 - tf_s // 60
            else:
                et_mod = close_slot = None
            exit_px = reason = t_exit = None
            cost_out = config.MAKER_FEE
            exit_k = None

            stop = tr["stop_px"]            # atrstop siempre; flip/meanrev solo si safety_atr
            for k in range(i0, len(df)):
                if stop:
                    hit = lo[k] <= stop if side > 0 else hi[k] >= stop
                    if hit:
                        exit_px = min(op[k], stop) if side > 0 else max(op[k], stop)
                        reason, cost_out = "SL", config.TAKER_FEE + config.SLIPPAGE
                        t_exit = df.index[k]; exit_k = k
                        break
                # ORB: vela de cierre de sesión -> salir a su cierre (mismo día de entrada)
                if et_mod is not None and et_mod[k] >= close_slot:
                    exit_px, t_exit, reason, exit_k = cl[k], df.index[k], "session_close", k
                    break
                # salida por senal (flip ST contrario / reversion a la media): prioritaria al timeout
                if flip is not None and flip[k]:
                    exit_px, t_exit = (op[k + 1], df.index[k + 1]) if k + 1 < len(df) \
                        else (live_open, None)
                    reason = "revert" if strat.exit_mode == "meanrev" else "flip"
                    exit_k = k
                    break
                if has_timeout and k - i0 + 1 >= to_bars:
                    exit_px, t_exit = (op[k + 1], df.index[k + 1]) if k + 1 < len(df) \
                        else (live_open, None)
                    reason = "timeout"; exit_k = k
                    break
            # fallback: trade mas viejo que la ventana de datos -> timeout por reloj
            if exit_px is None and tr["timeout_at"] \
                    and _now() >= datetime.fromisoformat(tr["timeout_at"]) \
                    and entry_bar_start < starts[0]:
                exit_px, reason = live_open, "timeout"

            if exit_px is not None:
                extra = {}
                if exit_k is not None:
                    seg_hi = float(hi[i0:exit_k + 1].max()); seg_lo = float(lo[i0:exit_k + 1].min())
                    ep = tr["entry_px"]
                    if side > 0:
                        mfe, mae = seg_hi / ep - 1, seg_lo / ep - 1
                    else:
                        mfe, mae = ep / seg_lo - 1, ep / seg_hi - 1
                    sd = abs(ep - tr["stop_px"]) / ep if tr.get("stop_px") else None
                    extra = {"mae_pct": round(mae * 100, 4), "mfe_pct": round(mfe * 100, 4),
                             "mae_r": round(mae / sd, 3) if sd else None,
                             "mfe_r": round(mfe / sd, 3) if sd else None,
                             "exit_slippage_bps": round(config.SLIPPAGE * 1e4, 1) if reason == "SL" else 0.0}
                    # contrafactuales de salida: MISMAS velas, otras reglas. No tocan la ejecución
                    # (ver shadow.py) — alimentan la decisión de stops/objetivos con datos OOS.
                    sh = shadow.compute(side, tr["entry_px"], tr["stop_px"], (op, hi, lo, cl), i0,
                                        to_bars if has_timeout else None, flip,
                                        et_mod, close_slot, live_open)
                    if sh:
                        extra["shadow_exits"] = json.dumps(sh)
                self._close(tr, float(exit_px), reason, cost_out, t_exit, extra)

    def _close(self, tr, exit_px, reason, cost_out, t_exit=None, extra=None):
        side = 1 if tr["side"] == "long" else -1
        notional, margin = tr["notional"], tr["base_amount"]
        entry_t = datetime.fromisoformat(tr["t_entry"])
        exit_dt = t_exit.to_pydatetime().astimezone(config.LIMA_TZ) if t_exit is not None else _now()
        gross_pct = side * (exit_px / tr["entry_px"] - 1)
        fees_usd = (config.MAKER_FEE + cost_out) * notional
        fund_sum = data.funding_since(tr["symbol"], entry_t.timestamp() * 1000,
                                      exit_dt.timestamp() * 1000)
        funding_usd = -side * fund_sum * notional        # long paga si funding>0; short cobra
        pnl = gross_pct * notional - fees_usd + funding_usd
        ret_nolev = pnl / notional
        ret_lev = pnl / margin
        bars_held = int((exit_dt - entry_t).total_seconds() // _TF_S[tr["tf"]])
        db.close_trade(tr["id"], t_exit=_iso(exit_dt), exit_px=exit_px, exit_reason=reason,
                       pnl_usd=round(pnl, 4), fees_usd=round(fees_usd, 4),
                       funding_usd=round(funding_usd, 4),
                       ret_pct_lev=round(ret_lev * 100, 4),
                       ret_pct_nolev=round(ret_nolev * 100, 4), bars_held=bars_held,
                       **(extra or {}))
        db.log_signal(tr["strategy_id"], tr["symbol"], "exit",
                      {"reason": reason, "px": exit_px, "pnl": round(pnl, 2)})
        db.log_event("info", "trade",
                     f"{tr['strategy_id']} cierra {tr['side']} {tr['symbol']} @ {exit_px} "
                     f"({reason}) PnL ${pnl:+.2f}")

    # ---------- entradas ----------
    def _manage_entries(self, market, due_tfs):
        open_by_strat = {t["strategy_id"] for t in db.open_trades()}
        for s in _ALL:
            if s.tf not in due_tfs or (s.symbol, s.tf) not in market:
                continue
            if getattr(s, "session", "24/7") == "us" and not data.in_us_session():
                continue                           # titulares 'us' solo ABREN durante la sesión US
            raw_df, live_open = market[(s.symbol, s.tf)]
            df = _view(s, raw_df)                  # titular 'us' evalúa solo sobre barras de sesión US
            if len(df) < 30:
                continue
            try:
                signal = s.entry_signal(df)
            except Exception as e:
                db.log_event("error", "signal", f"{s.sid} error evaluando senal: {e}")
                continue
            if not signal:
                continue
            # --- Gate de regimen: los LONGS de cripto solo entran con BTC en regimen alcista
            # (close diario > SMA200). En vivo (n=89) los longs sangraron -234 vs shorts +73:
            # era beta bajista de mercado, no alpha. Los shorts NO se filtran. Los 'stocks'
            # tampoco (BTC no gobierna equities — necesitan su propio gate de indice).
            if s.side > 0 and s.asset_class == "crypto" and not _btc_bull():
                db.log_signal(s.sid, s.symbol, "entry_skipped", {"motivo": "btc_bear_regime"})
                continue
            if s.sid in open_by_strat:
                db.log_signal(s.sid, s.symbol, "entry_skipped", {"motivo": "posicion abierta"})
                continue
            self._open(s, df, float(live_open))

    def _entry_context(self, s, df):
        """Datos de contexto al entrar — valiosos para decidir si la estrategia se queda o se va."""
        ctx = {}
        try:
            c = df["close"]; price = float(c.iloc[-1])
            ctx["entry_atr_pct"] = round(float(atr14(df).iloc[-1]) / price * 100, 4) if price else None
            sma200 = c.rolling(200).mean().iloc[-1]
            ctx["entry_trend_dist"] = round(price / float(sma200) - 1, 5) if sma200 == sma200 else None
            ctx["entry_hour"] = _now().hour
            ctx["entry_vol_regime"] = int(bool(I.vol_ok(df)[-1]))
            _, _, regup, regdn = I.bx_parts(c)
            ctx["entry_regime_ok"] = int(bool(regup[-1] if s.side > 0 else regdn[-1]))
        except Exception as e:
            db.log_event("warn", "context", f"{s.sid} contexto de entrada parcial: {e}")
        try:
            now_ms = datetime.now(config.LIMA_TZ).timestamp() * 1000
            ctx["entry_funding"] = round(data.funding_since(s.symbol, now_ms - 9 * 3600 * 1000, now_ms), 6)
        except Exception:
            pass
        return ctx

    def _open(self, s, df, entry_px):
        ctx = self._entry_context(s, df)
        atr = float(atr14(df).iloc[-1])
        if s.entry_stop_fn is not None:                  # ORB: stop = OR-low (no ATR)
            stop_px = s.entry_stop_fn(df, entry_px)
        else:
            atr_mult = config.ATR_MULT if s.exit_mode == "atrstop" else s.safety_atr
            stop_px = entry_px - (1 if s.side > 0 else -1) * atr_mult * atr \
                if atr_mult else None
        # --- sizing ---
        # FASE DE MEDICIÓN (SIZING_MODE='flat'): nocional constante. Cada trade pesa IGUAL en el
        # PnL, así el dólar es un estimador limpio del edge en vez de una mezcla de edge y leverage.
        # (Con sizing por riesgo, cripto-short daba +88 USD con 0.0 bps/trade: el dólar venía del
        # leverage variable, no del edge — auditoría 03/08/2026.) El leverage óptimo por estrategia
        # se calibra DESPUÉS, cuando una tesis esté aprobada como rentable.
        margin = self.capital0 * config.MARGIN_PCT          # margen fijo ($100)
        stop_dist = abs(entry_px - stop_px) / entry_px if (stop_px and entry_px) else None
        if config.SIZING_MODE == "flat":
            leverage = config.FLAT_LEVERAGE
        elif stop_dist and stop_dist > 0:
            risk_usd = self.capital0 * config.RISK_PER_TRADE          # arriesga 0.5% si toca stop
            leverage = risk_usd / (stop_dist * margin)               # leverage para ese riesgo
            leverage = min(config.MAX_LEVERAGE, max(1.0, leverage))   # cap de seguridad
        else:
            leverage = config.LEVERAGE                                # fallback (sin stop): 5x
        notional = margin * leverage
        qty = notional / entry_px
        timeout_at = _iso(_now() + timedelta(hours=(s.timeout_h or config.TIMEOUT_HOURS))) \
            if s.exit_mode in ("atrstop", "meanrev") else None
        tid = db.insert_trade(
            strategy_id=s.sid, strategy_name=s.name, symbol=s.symbol, tf=s.tf,
            side="long" if s.side > 0 else "short", status="open", asset_class=s.asset_class,
            t_signal=_iso(df.index[-1].to_pydatetime().astimezone(config.LIMA_TZ)),
            t_entry=db.utcnow(),
            entry_px=entry_px, base_amount=margin, leverage=round(leverage, 2),
            notional=notional, qty=qty, stop_px=stop_px, timeout_at=timeout_at,
            atr_entry=atr, signal_meta=json.dumps({"exit_mode": s.exit_mode}), **ctx)
        db.log_signal(s.sid, s.symbol, "entry", {"px": entry_px, "trade_id": tid})
        db.log_event("info", "trade",
                     f"{s.sid} abre {'long' if s.side > 0 else 'short'} {s.symbol} @ {entry_px} "
                     f"(margen ${margin:.0f} x{leverage:.1f} = ${notional:.0f} nocional, R={config.RISK_PER_TRADE*100:.2f}%)")

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
