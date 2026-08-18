"""Research: indicadores NUEVOS no probados (batch 1) sobre las 52 monedas del store.

Pruebo dos generadores de senal de clase distinta al roster (que es casi todo MA-trend:
Supertrend/Ribbon/B-Xtrender/TrendMeter), buscando edge ORTOGONAL:

  1) Squeeze Momentum (LazyBear): BB dentro de KC = compresion; la senal es el RELEASE
     (squeeze off) en la direccion del momentum (linreg). Clase: ruptura de volatilidad.
  2) Vortex (VI+/VI-): cruce de VI+ sobre VI- = inicio de tendencia alcista (y viceversa).
     Clase: movimiento direccional (math distinta a Supertrend).

Ambas son senales de continuacion/ruptura -> casan con el motor de salida del harness
(ATR-stop 2x + timeout 48h). Mean-reversion (Connors/RSI2) NO entra aqui: su exit es otro.

Pipeline IDENTICO al que produjo S10-S21 (expandir_universo.py):
  - entrada open[i+1]; SL 2xATR + timeout 48h; funding real; costos maker/taker+slip.
  - filtros de conviccion: trend(EMA200), vol(ATR%>=mediana), sweep6(barrido<=6), regime(B-X).
  - GATE: exp_neto>0, PF>=1.4, n>=40, todos los anios+ (tol 1). Reporta corr vs PnL del roster.

Uso: python poc_indicadores_nuevos.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import os
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_sweep_filter.py"), encoding="utf-8").read()
exec(src.split("TFMAP =")[0])   # I, DATA, MAKER, TAKER, SLIP, WARM, detect_sweeps, recent, roster_entries, run

FUND = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"
STORE = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm"
ROSTER_COINS = ["TRX", "XRP", "AVAX", "BTC", "SUI", "LTC", "ETH"]
FILTER_SETS = [[], ["trend"], ["vol"], ["sweep6"], ["regime"], ["trend", "vol"], ["sweep6", "trend"]]


def all_coins():
    return sorted(d.split("_")[0] for d in os.listdir(STORE) if d.endswith("_USDT_USDT"))


def load_fund(coin):
    f = pd.read_parquet(FUND.format(c=coin)).sort_values("ts")
    return f["ts"].values.astype(float), f["funding_rate"].values.astype(float)


def run_f(df, side, exit_mode, safety_atr, entry, flips, tf, ft, fr):
    """run() con FUNDING real acumulado por trade (paridad engine.py)."""
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atr = I.atr14(df).values; idx = df.index; n = len(df)
    up, dn = flips; flip_arr = (dn if side > 0 else up)
    to_bars = int(48 * 3600 / (900 if tf == "15m" else 3600))
    amult = 2.0 if exit_mode == "atrstop" else safety_atr
    ivms = idx.view("int64") / 1e6
    trades = []; i = WARM
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]
        stop = epx - side * amult * atr[i] if amult else None
        exit_px = cost_out = t_out = None; j = e_i
        while j < n - 1:
            if stop is not None:
                hit = lo[j] <= stop if side > 0 else hi[j] >= stop
                if hit:
                    exit_px = min(op[j], stop) if side > 0 else max(op[j], stop)
                    cost_out, t_out = TAKER + SLIP, j; break
            if exit_mode == "atrstop":
                if j - e_i + 1 >= to_bars:
                    exit_px, cost_out, t_out = op[j + 1], MAKER, j + 1; break
            elif flip_arr[j]:
                exit_px, cost_out, t_out = op[j + 1], MAKER, j + 1; break
            j += 1
        if exit_px is None:
            break
        a, b = np.searchsorted(ft, ivms[e_i]), np.searchsorted(ft, ivms[t_out])
        net = side * (exit_px / epx - 1) - MAKER - cost_out - side * fr[a:b].sum()
        trades.append((idx[e_i], net)); i = j + 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None


def met(tr):
    if tr is None or len(tr) == 0:
        return None
    r = tr["ret"]; by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), wr=(r > 0).mean()*100, exp=r.mean()*1e4,
                pf=r[r > 0].sum()/max(abs(r[r <= 0].sum()), 1e-9),
                ypos=int((by > 0).sum()), ytot=int(len(by)))


# ---------- INDICADORES NUEVOS (Pine-fieles) ----------
def _tr(df):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def _linreg_end(y, n):
    """Valor del extremo (offset 0) de la regresion lineal sobre las ultimas n barras.
    Pine linreg(y,n,0) = intercept + slope*(n-1). Vectorizado con sumas rolling."""
    y = pd.Series(y).reset_index(drop=True)
    t = np.arange(len(y), dtype=float)
    Sy = y.rolling(n).sum()
    Spy = (pd.Series(t) * y).rolling(n).sum()           # sum(global_pos * y)
    oldest = t - (n - 1)                                # indice global del mas viejo del window
    Sky = Spy - oldest * Sy                             # sum(k*y), k=0..n-1 dentro del window
    Sk = n * (n - 1) / 2.0
    Skk = (n - 1) * n * (2 * n - 1) / 6.0
    denom = n * Skk - Sk * Sk
    slope = (n * Sky - Sk * Sy) / denom
    intercept = (Sy - slope * Sk) / n
    return (intercept + slope * (n - 1)).values


def squeeze_momentum(df, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5):
    """LazyBear Squeeze Momentum. Devuelve (long_event, short_event).
    Senal = RELEASE del squeeze (sqzOn->off) en la direccion del momentum val."""
    c, h, l = df["close"], df["high"], df["low"]
    basis = c.rolling(bb_len).mean(); dev = bb_mult * c.rolling(bb_len).std(ddof=0)
    upBB, loBB = basis + dev, basis - dev
    ma = c.rolling(kc_len).mean(); rangema = _tr(df).rolling(kc_len).mean()
    upKC, loKC = ma + rangema * kc_mult, ma - rangema * kc_mult
    sqz_on = (loBB > loKC) & (upBB < upKC)
    # momentum: linreg(close - avg(avg(hh,ll), sma(close)), n)
    hh = h.rolling(kc_len).max(); ll = l.rolling(kc_len).min()
    avg1 = (hh + ll) / 2.0; src = c - (avg1 + c.rolling(kc_len).mean()) / 2.0
    val = _linreg_end(src, kc_len)
    release = sqz_on.shift(1).fillna(False).values & (~sqz_on.values)   # squeeze termina ESTA barra
    longe = release & (val > 0)
    shorte = release & (val < 0)
    return longe, shorte


def vortex(df, n=14):
    """Vortex VI+/VI-. Senal = cruce (evento). Devuelve (long_event, short_event)."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    vmp = (h - l.shift(1)).abs(); vmm = (l - h.shift(1)).abs()
    str_ = tr.rolling(n).sum()
    vip = (vmp.rolling(n).sum() / str_).values
    vim = (vmm.rolling(n).sum() / str_).values
    up_cross = (vip > vim) & (np.roll(vip, 1) <= np.roll(vim, 1))
    dn_cross = (vip < vim) & (np.roll(vip, 1) >= np.roll(vim, 1))
    up_cross[0] = dn_cross[0] = False
    return up_cross, dn_cross


SIGNALS = {
    # nombre: (funcion -> (long_evt, short_evt), exit_mode, safety_atr)
    "SQZ": (squeeze_momentum, "atrstop", None),
    "VTX": (vortex, "atrstop", None),
}


def filt_arrays(df, side):
    c = df["close"]; _, _, regup, regdn = I.bx_parts(c)
    ema = c.ewm(span=200, adjust=False).mean().values
    atr = I.atr14(df).values; atrpct = atr / c.values
    volmed = pd.Series(atrpct).rolling(500, min_periods=100).median().values
    sL, sS = detect_sweeps(df)
    return {"trend": (c.values > ema) if side > 0 else (c.values < ema),
            "vol": atrpct >= volmed,
            "sweep6": recent(sL if side > 0 else sS, 6),
            "regime": (np.asarray(regup) if side > 0 else np.asarray(regdn))}


def roster_pnl_daily():
    daily = []
    for coin in ROSTER_COINS:
        for tf in ("1h", "15m"):
            df = pd.read_parquet(DATA.format(c=coin, tf=tf))
            df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
            ents, flips = roster_entries(coin, df); ft, fr = load_fund(coin)
            tfmap = {"S3-TRX-L": "15m", "S7-AVAX-L": "15m"}
            for sid, (side, em, sa, entry) in ents.items():
                if tfmap.get(sid, "1h") != tf:
                    continue
                tr = run_f(df, side, em, sa, entry, flips, tf, ft, fr)
                if tr is not None:
                    daily.append(tr.set_index("t_in")["ret"].resample("1D").sum())
    return pd.concat(daily, axis=1).fillna(0).sum(axis=1)


def main():
    coins = all_coins()
    print(f"Universo: {len(coins)} monedas · TF 1h · senales: {', '.join(SIGNALS)}", flush=True)
    R = roster_pnl_daily()
    survivors = []
    for ci, coin in enumerate(coins, 1):
        try:
            df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        except Exception:
            continue
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        try:
            ft, fr = load_fund(coin)
        except Exception:
            continue
        up, dn, _ = I.st_flips(df); flips = (up, dn)
        for sname, (fn, em, sa) in SIGNALS.items():
            longe, shorte = fn(df)
            for side, evt, tag in ((+1, longe, "L"), (-1, shorte, "S")):
                fa = filt_arrays(df, side)
                best = None
                for fs in FILTER_SETS:
                    mask = np.ones(len(df), bool)
                    for f in fs:
                        mask &= fa[f]
                    tr = run_f(df, side, em, sa, np.asarray(evt) & mask, flips, "1h", ft, fr)
                    m = met(tr)
                    if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.4 or m["ypos"] < m["ytot"] - 1:
                        continue
                    if best is None or m["exp"] > best[2]["exp"]:
                        best = (fs, tr, m)
                if best:
                    fs, tr, m = best
                    d = tr.set_index("t_in")["ret"].resample("1D").sum()
                    al = pd.concat([d, R], axis=1).fillna(0)
                    corr = al.iloc[:, 0].corr(al.iloc[:, 1])
                    survivors.append((coin, f"{sname}-{tag}", fs, m, corr))
        print(f"  [{ci}/{len(coins)}] {coin}", end="\r", flush=True)

    print(" " * 40)
    print(f"{'='*96}")
    print(f"SUPERVIVIENTES (exp_neto>0, PF>=1.4, n>=40, anios+ tol1)  ·  indicadores NUEVOS")
    print(f"{'coin':6}{'senal':9}{'filtros':20}{'n':>5}{'WR%':>5}{'exp':>7}{'PF':>6}{'años+':>7}{'corr':>7}")
    print(f"{'-'*96}")
    for coin, sig, fs, m, corr in sorted(survivors, key=lambda x: x[3]["exp"], reverse=True):
        print(f"{coin:6}{sig:9}{('+'.join(fs) or 'ninguno'):20}{m['n']:5}{m['wr']:5.0f}"
              f"{m['exp']:7.0f}{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{corr:7.2f}")
    if survivors:
        print(f"\n{len(survivors)} setups. corr media vs roster: "
              f"{np.mean([s[4] for s in survivors]):.2f}  ·  "
              f"low-corr (<0.2): {sum(1 for s in survivors if abs(s[4]) < 0.2)}")
    else:
        print("\n0 setups pasaron el gate.")


if __name__ == "__main__":
    main()
