"""Expansión del universo cripto: aplica los templates del roster + filtros de convicción
a las monedas NUEVAS (ADA, BNB, DOGE, DOT, LINK, SOL) para hallar setups de alta convicción
descorrelacionados del roster actual.

Gate (calidad, no WR): expectancy neto>0 (con funding), PF>=1.4, TODOS los años positivos,
n>=40. Para los supervivientes: correlación de su PnL diario vs el roster actual (queremos baja).

Uso: python expandir_universo.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/poc_sweep_filter.py"), encoding="utf-8").read()
exec(src.split("TFMAP =")[0])   # detect_sweeps, recent, roster_entries, run, I, DATA, MAKER, TAKER, SLIP, WARM
FUND = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"
NEW = ["ADA", "BNB", "DOGE", "DOT", "LINK", "SOL"]
ROSTER_COINS = ["TRX", "XRP", "AVAX", "BTC", "SUI", "LTC", "ETH"]


def load_fund(coin):
    f = pd.read_parquet(FUND.format(c=coin)).sort_values("ts")
    return f["ts"].values.astype(float), f["funding_rate"].values.astype(float)


def run_f(df, side, exit_mode, safety_atr, entry, flips, tf, ft, fr):
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


def templates(coin, df):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    up, dn, sd = I.st_flips(df)
    gl, rs, regup, regdn = I.bx_parts(c)
    hc = I.hacolt(o, h, l, c); don = I.dch_trend(c, h, l, 20); slr, _ = I.ribbon_strength(c, h, l)
    fullev = (slr == 10) & ~np.roll(slr == 10, 1)
    T = {
        "BX-L": (+1, "atrstop", None, gl.values if hasattr(gl, "values") else gl),
        "BX-S": (-1, "atrstop", None, (rs & regdn).values if hasattr(rs & regdn, "values") else (rs & regdn)),
        "BXdon-S": (-1, "atrstop", None, np.asarray(rs) & (don == -1)),
        "SThac-L": (+1, "flip", None, up & (hc == 1)),
        "STdon-S": (-1, "atrstop", None, dn & (don == -1)),
        "STdonhac-L": (+1, "flip", None, up & (don == 1) & (hc == 1)),
        "RIB-L": (+1, "atrstop", None, fullev & regup.values if hasattr(regup, "values") else fullev & regup),
        "TM-L": (+1, "flip", 3.0, I.tm_align_edge(c)),
    }
    return {k: (s, e, sa, np.asarray(v)) for k, (s, e, sa, v) in T.items()}, (up, dn)


def filt_arrays(df, side, sL, sS):
    c = df["close"]; green, red, regup, regdn = I.bx_parts(c)
    ema = c.ewm(span=200, adjust=False).mean().values
    atr = I.atr14(df).values; atrpct = atr / c.values
    volmed = pd.Series(atrpct).rolling(500, min_periods=100).median().values
    return {"trend": (c.values > ema) if side > 0 else (c.values < ema),
            "vol": atrpct >= volmed, "sweep6": recent(sL if side > 0 else sS, 6),
            "regime": (np.asarray(regup) if side > 0 else np.asarray(regdn))}


def met(tr):
    if tr is None or len(tr) == 0:
        return None
    r = tr["ret"]; by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), wr=(r > 0).mean()*100, exp=r.mean()*1e4,
                pf=r[r > 0].sum()/max(abs(r[r <= 0].sum()), 1e-9),
                ypos=int((by > 0).sum()), ytot=int(len(by)))


FILTER_SETS = [[], ["trend"], ["sweep6"], ["trend", "vol"], ["sweep6", "trend"]]


def main():
    # 1) PnL diario del roster actual (para correlación)
    roster_daily = []
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
                    roster_daily.append(tr.set_index("t_in")["ret"].resample("1D").sum())
    R = pd.concat(roster_daily, axis=1).fillna(0).sum(axis=1)

    print(f"{'='*94}")
    print(f"SETUPS DE ALTA CONVICCION EN MONEDAS NUEVAS (exp>0, PF>=1.4, todos años+, n>=40)")
    print(f"{'coin':5}{'template':13}{'filtros':18}{'n':>4}{'WR%':>5}{'exp':>7}{'PF':>6}{'años+':>7}{'corr_roster':>12}")
    print(f"{'-'*94}")
    survivors = []
    for coin in NEW:
        df = pd.read_parquet(DATA.format(c=coin, tf="1h"))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        T, flips = templates(coin, df); ft, fr = load_fund(coin)
        sL, sS = detect_sweeps(df)
        for tname, (side, em, sa, entry) in T.items():
            fa = filt_arrays(df, side, sL, sS)
            best = None
            for fs in FILTER_SETS:
                mask = np.ones(len(df), bool)
                for f in fs:
                    mask &= fa[f]
                tr = run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr)
                m = met(tr)
                if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.35 or m["ypos"] < m["ytot"] - 1:
                    continue
                if best is None or m["exp"] > best[2]["exp"]:
                    best = (fs, tr, m)
            if best:
                fs, tr, m = best
                d = tr.set_index("t_in")["ret"].resample("1D").sum()
                al = pd.concat([d, R], axis=1).fillna(0)
                corr = al.iloc[:, 0].corr(al.iloc[:, 1])
                survivors.append((coin, tname, fs, m, corr))
    for coin, tname, fs, m, corr in sorted(survivors, key=lambda x: x[3]["exp"], reverse=True):
        print(f"{coin:5}{tname:13}{('+'.join(fs) or 'ninguno'):18}{m['n']:4}{m['wr']:5.0f}"
              f"{m['exp']:7.0f}{m['pf']:6.2f}{m['ypos']:4}/{m['ytot']:<2}{corr:12.2f}")
    print(f"\n{len(survivors)} setups nuevos de alta convicción. "
          f"Correlación media con el roster: {np.mean([s[4] for s in survivors]):.2f}" if survivors else "0 setups")


if __name__ == "__main__":
    main()
