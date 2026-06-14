"""
PoC honesto — CME Gap Fill aplicado al estandar de tvbot.

Tesis (de Sentinel/btc): el CME (futuro BTC/ETH regulado) cierra el viernes y reabre
el lunes; Binance opera 24/7. El hueco entre el cierre CME del viernes y el precio
Binance del lunes tiende a "llenarse" (Binance se mueve hacia el precio CME).

Por que este PoC y no el de Sentinel:
- El backtest original usaba P&L en multiplos de R IDEALIZADOS (T1+BE=+0.75R fijo),
  SIN fees, SIN funding, SIN slippage, SIN fills reales. Aqui aplicamos el MISMO modelo
  de costos del bot en produccion (maker/taker+slip + funding real) y entrada al open de
  vela, igual que tvbot. Veredicto honesto: ¿sobrevive el gap-fill a los costos?

Solo BTC y ETH: son las unicas de nuestro universo con futuro CME e historial real en
yfinance (BTC=F, ETH=F). SOL/XRP tienen contrato CME pero yfinance no trae su historia;
TRX/SUI/LTC/AVAX no tienen futuro CME -> no hay gap que llenar.

Salida: tabla por moneda y por año (OOS), con y sin costos para aislar el drag.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

# ---- costos identicos a tvbot/config.py (paridad con produccion) ----
MAKER_FEE = 0.0002
TAKER_FEE = 0.00045
SLIPPAGE  = 0.0002

STORE = "C:/Users/LENOVO/Oscilion/data"
UTC = timezone.utc

# ---- parametros del setup (defaults afinados del proyecto original) ----
ENTRY_H_LIMA  = 3       # lunes 3am Lima = 08:00 UTC (apertura Europa)
STOP_FACTOR   = 1.0     # stop = entry -/+ 1.0 x gap
T1_RATIO      = 0.33    # T1 = 33% del gap
MAX_BARS      = 35      # lunes 3am -> martes 2pm Lima (~35h)
MIN_GAP_PCTS  = [0.3, 0.5, 0.8, 1.2]   # sensibilidad del umbral de gap (% del precio)


# ───────────────────────── datos ─────────────────────────

def load_ohlcv(coin: str) -> pd.DataFrame:
    df = pd.read_parquet(f"{STORE}/ohlcv/binanceusdm/{coin}_USDT_USDT/1h.parquet")
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def load_funding(coin: str) -> pd.DataFrame:
    f = pd.read_parquet(f"{STORE}/funding/binanceusdm/{coin}_USDT_USDT.parquet")
    return f.sort_values("ts").reset_index(drop=True)


def funding_since(fund: pd.DataFrame, t0_ms: float, t1_ms: float) -> float:
    """Suma funding_rate de las ventanas en (t0, t1]. Long paga si rate>0."""
    if t1_ms <= t0_ms:
        return 0.0
    ts = fund["ts"].to_numpy()
    lo = np.searchsorted(ts, t0_ms, side="right")
    hi = np.searchsorted(ts, t1_ms, side="right")
    return float(fund["funding_rate"].to_numpy()[lo:hi].sum())


def load_cme_fridays(ticker: str) -> dict:
    """{date_viernes: cierre_CME} via yfinance."""
    import yfinance as yf
    df = yf.download(ticker, start="2023-01-01", progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"yfinance vacio para {ticker}")
    cl = df["Close"]
    cl = cl[cl.columns[0]] if hasattr(cl, "columns") else cl
    out = {}
    for idx, val in cl.items():
        v = float(val)
        if hasattr(idx, "weekday") and idx.weekday() == 4 and not np.isnan(v):
            out[idx.date()] = v
    return out


# ───────────────────────── simulacion honesta ─────────────────────────

def simulate(op, hi, lo, cl, i0, entry, stop, t1, t2, side, max_bars):
    """All-out: sale en SL (taker+slip), T2/fill (maker) o timeout (maker).
    Desempate pesimista: si SL y T2 caen en la misma vela, gana el SL.
    Devuelve (exit_px, reason, cost_out, exit_idx, hit_t1)."""
    end = min(i0 + max_bars, len(op))
    hit_t1 = False
    for k in range(i0, end):
        if side > 0:
            at_sl, at_t2 = lo[k] <= stop, hi[k] >= t2
            if hi[k] >= t1:
                hit_t1 = True
        else:
            at_sl, at_t2 = hi[k] >= stop, lo[k] <= t2
            if lo[k] <= t1:
                hit_t1 = True
        if at_sl:
            return stop, "SL", TAKER_FEE + SLIPPAGE, k, hit_t1
        if at_t2:
            return t2, "fill", MAKER_FEE, k, hit_t1
    return cl[end - 1], "timeout", MAKER_FEE, end - 1, hit_t1


def net_return(side, entry, exit_px, cost_out, fund_sum):
    """Retorno neto como fraccion del nominal, identico al _close de tvbot."""
    gross = side * (exit_px / entry - 1)
    fees  = MAKER_FEE + cost_out
    return gross - fees - side * fund_sum          # long paga funding>0


# ───────────────────────── evaluador ─────────────────────────

def _ema(arr, span):
    if len(arr) < span:
        return None
    return float(pd.Series(arr).ewm(span=span, adjust=False).mean().iloc[-1])


def eval_coin(coin, ticker, min_gap_pct, require_s1=False):
    df   = load_ohlcv(coin)
    fund = load_funding(coin)
    cme  = load_cme_fridays(ticker)

    ts = df["ts"].to_numpy()
    op, hi, lo, cl = (df[c].to_numpy() for c in ("open", "high", "low", "close"))
    trades = []

    for friday, cme_close in sorted(cme.items()):
        monday = friday + timedelta(days=3)
        target = datetime(monday.year, monday.month, monday.day,
                          ENTRY_H_LIMA + 5, 0, tzinfo=UTC)        # 3am Lima = 08:00 UTC
        target_ms = target.timestamp() * 1000
        i0 = int(np.searchsorted(ts, target_ms))
        if i0 >= len(ts) or ts[i0] != target_ms:
            continue                                              # sin vela exacta de entrada
        entry = op[i0]
        gap = entry - cme_close
        gap_abs = abs(gap)
        gap_pct = gap_abs / cme_close * 100
        if gap_pct < min_gap_pct:
            continue
        side = -1 if gap > 0 else 1                               # precio>CME -> short al fill

        if require_s1:                                            # S1: EMA9/21 1h alineado al fill
            e9, e21 = _ema(cl[:i0], 9), _ema(cl[:i0], 21)
            if e9 is None or e21 is None:
                continue
            margin = entry * 0.0020                               # 0.20% "recuperando cruce"
            s1_ok = (e9 > e21 or 0 <= e21 - e9 <= margin) if side > 0 \
                else (e9 < e21 or 0 <= e9 - e21 <= margin)
            if not s1_ok:
                continue

        risk = STOP_FACTOR * gap_abs
        if side > 0:
            stop, t1, t2 = entry - risk, entry + T1_RATIO * gap_abs, cme_close
        else:
            stop, t1, t2 = entry + risk, entry - T1_RATIO * gap_abs, cme_close

        exit_px, reason, cost_out, kx, hit_t1 = simulate(
            op, hi, lo, cl, i0, entry, stop, t1, t2, side, MAX_BARS)
        fsum = funding_since(fund, ts[i0], ts[kx])
        ret_net   = net_return(side, entry, exit_px, cost_out, fsum)
        ret_gross = side * (exit_px / entry - 1)                  # sin costos ni funding
        r_net = (side * (exit_px - entry) - (MAKER_FEE + cost_out) * entry
                 - side * fsum * entry) / risk
        trades.append({
            "coin": coin, "date": datetime.fromtimestamp(ts[i0] / 1000, UTC),
            "year": datetime.fromtimestamp(ts[i0] / 1000, UTC).year,
            "side": "L" if side > 0 else "S", "gap_pct": gap_pct,
            "reason": reason, "bars": kx - i0, "hit_t1": hit_t1,
            "ret_net": ret_net, "ret_gross": ret_gross, "r_net": r_net,
        })
    return pd.DataFrame(trades)


def metrics(t: pd.DataFrame) -> dict:
    n = len(t)
    if n == 0:
        return {"n": 0}
    wins = (t["ret_net"] > 0).sum()
    comp = float(np.prod(1 + t["ret_net"].to_numpy()) - 1)
    return {
        "n": n,
        "long%": round((t["side"] == "L").mean() * 100, 0),
        "win%": round(wins / n * 100, 1),
        "fill%": round((t["reason"] == "fill").mean() * 100, 1),
        "SL%": round((t["reason"] == "SL").mean() * 100, 1),
        "TO%": round((t["reason"] == "timeout").mean() * 100, 1),
        "avg_net%": round(t["ret_net"].mean() * 100, 3),
        "avg_gross%": round(t["ret_gross"].mean() * 100, 3),
        "exp_R": round(t["r_net"].mean(), 3),
        "comp%": round(comp * 100, 1),
        "avg_bars": round(t["bars"].mean(), 1),
    }


def show(title, t):
    m = metrics(t)
    print(f"\n=== {title} ===")
    if m["n"] == 0:
        print("  (0 trades)")
        return
    print(f"  trades={m['n']}  long={m['long%']:.0f}%  win={m['win%']}%  "
          f"avg_bars={m['avg_bars']}")
    print(f"  salidas: fill={m['fill%']}%  SL={m['SL%']}%  timeout={m['TO%']}%")
    print(f"  avg neto/trade={m['avg_net%']}%  (sin costos={m['avg_gross%']}%)  "
          f"exp={m['exp_R']}R  compuesto={m['comp%']}%")


def main():
    min_gap = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    coins = [("BTC", "BTC=F"), ("ETH", "ETH=F")]

    print(f"\n########## CME GAP — PoC HONESTO (min_gap={min_gap}%) ##########")
    print(f"costos: maker {MAKER_FEE*100}% / taker+slip {(TAKER_FEE+SLIPPAGE)*100}% / funding real")
    print(f"setup: entry lun 3am Lima, stop {STOP_FACTOR}xgap, T1 {T1_RATIO*100:.0f}%gap, "
          f"T2=fill, timeout {MAX_BARS}h")

    pooled = []
    for coin, tk in coins:
        t = eval_coin(coin, tk, min_gap)
        pooled.append(t)
        show(f"{coin}  (todos los años)", t)
        for y in sorted(t["year"].unique()):
            show(f"{coin}  {y}", t[t["year"] == y])

    allt = pd.concat(pooled, ignore_index=True)
    show("POOL BTC+ETH  (todos los años)", allt)

    # mejor version: con filtro S1 (EMA9/21) — el mas discriminante segun el proyecto original
    s1t = pd.concat([eval_coin(c, tk, min_gap, require_s1=True) for c, tk in coins],
                    ignore_index=True)
    show("POOL BTC+ETH  CON FILTRO S1 (EMA9/21)", s1t)
    for y in sorted(s1t["year"].unique()):
        show(f"  S1  {y}", s1t[s1t["year"] == y])

    print("\n########## SENSIBILIDAD AL UMBRAL DE GAP (pool BTC+ETH) ##########")
    print(f"{'min_gap%':>9} {'n':>4} {'win%':>6} {'fill%':>6} {'avg_net%':>9} {'exp_R':>7} {'comp%':>8}")
    for g in MIN_GAP_PCTS:
        ps = [eval_coin(c, tk, g) for c, tk in coins]
        at = pd.concat(ps, ignore_index=True)
        m = metrics(at)
        print(f"{g:>9} {m['n']:>4} {m['win%']:>6} {m['fill%']:>6} "
              f"{m['avg_net%']:>9} {m['exp_R']:>7} {m['comp%']:>8}")


if __name__ == "__main__":
    main()
