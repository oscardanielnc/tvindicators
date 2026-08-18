"""Resumen integral de las 44 estrategias: per-estrategia (tr/mes, exp neto) + portafolio
combinado (vol-parity 1/σ): rentabilidad MENSUAL esperada (neta de ganancias y pérdidas),
maxDD, Sharpe, trades/mes totales. Uso: python gen_summary.py"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/valida_roster_completo.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])  # entry_array(S1-21), coin_arrays, COIN_TF, run_f, met, load_fund, DATA, I, filt_arrays, build_tr, TOP8, daily_pnl

from tvbot import strategies as STRAT

TOP8_SID = {f"S{22+i}": spec for i, spec in enumerate(TOP8)}  # S22..S29 -> (coin,sig,side,fs)
SIGFN = {"adx": I.adx_dmi, "sqz": I.squeeze_momentum, "cmf": I.cmf, "fi": I.force_index,
         "kst": I.kst, "ao": I.awesome_osc, "tsi": I.tsi, "zl": I.zero_lag_entry,
         "srb": I.sr_volume_break}
LATE = {  # S31-S44: (coin, sigfn, side, filtros)
    "S31": ("ARB", "adx", -1, ["trend", "vol"]), "S32": ("EGLD", "sqz", -1, ["sweep6"]),
    "S33": ("DOT", "adx", -1, ["sweep6"]), "S34": ("HBAR", "adx", -1, ["sweep6"]),
    "S35": ("FLOW", "sqz", -1, ["sweep6"]), "S36": ("AVAX", "adx", -1, ["sweep6"]),
    "S37": ("ORDI", "cmf", +1, ["trend", "vol"]), "S38": ("ORDI", "fi", +1, ["regime"]),
    "S39": ("LINK", "kst", +1, ["sweep6"]), "S40": ("NEO", "ao", +1, ["sweep6", "trend"]),
    "S41": ("ICP", "kst", -1, ["regime"]), "S42": ("NEAR", "ao", -1, ["sweep6"]),
    "S43": ("ALGO", "tsi", -1, ["sweep6", "trend"]), "S44": ("TAO", "ao", -1, ["trend", "vol"]),
    "S45": ("FIL", "zl", +1, ["sweep6"]), "S46": ("NEO", "zl", -1, ["sweep6", "trend"]),
    "S47": ("STX", "zl", -1, ["sweep6"]), "S48": ("CRV", "zl", -1, ["sweep6", "trend"]),
    "S49": ("TAO", "sqz", +1, ["trend", "vol"]), "S50": ("FET", "sqz", +1, ["trend", "vol"]),
    "S51": ("JUP", "ao", +1, ["trend", "vol"]),
    "S52": ("DOGE", "srb", +1, ["trend"]), "S53": ("FET", "srb", +1, ["vol"]),
    "S54": ("ARB", "srb", -1, ["regime"]), "S55": ("ALGO", "srb", +1, ["trend", "vol"]),
    "S56": ("INJ", "srb", +1, ["vol"]),
}
_DF = {}
def getdf(coin, tf="1h"):
    if (coin, tf) not in _DF:
        d = pd.read_parquet(DATA.format(c=coin, tf=tf))
        d["dt"] = pd.to_datetime(d["ts"], unit="ms"); _DF[(coin, tf)] = d.set_index("dt").sort_index()
    return _DF[(coin, tf)]


def run_mr_local(df, side, entry, target_ma, stop_atr, to_bars, ft, fr):
    op, hi, lo, cl = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    atr = I.atr14(df).values; idx = df.index; ivms = idx.view("int64") / 1e6; n = len(df)
    tgt = np.asarray(target_ma); trades = []; i = 300
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]; stop = epx - side * stop_atr * atr[i]
        ex = co = to = None; j = e_i
        while j < n - 1:
            if (lo[j] <= stop if side > 0 else hi[j] >= stop):
                ex = min(op[j], stop) if side > 0 else max(op[j], stop); co, to = TAKER + SLIP, j; break
            if (cl[j] >= tgt[j] if side > 0 else cl[j] <= tgt[j]):
                ex, co, to = op[j + 1], MAKER, j + 1; break
            if j - e_i + 1 >= to_bars:
                ex, co, to = op[j + 1], MAKER, j + 1; break
            j += 1
        if ex is None:
            break
        a, b = np.searchsorted(ft, ivms[e_i]), np.searchsorted(ft, ivms[to])
        trades.append((idx[e_i], side * (ex / epx - 1) - MAKER - co - side * fr[a:b].sum())); i = j + 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None


def tr_for(sid):
    s = STRAT.BY_ID[sid]; coin = s.coin
    if sid in COIN_TF:                      # S1-S21
        co, tf, side, em, sa = COIN_TF[sid]; df = getdf(co, tf); ft, fr = load_fund(co)
        A = coin_arrays(co, df); ent = np.asarray(entry_array(sid, A))
        flips = (A["up"], A["tm_red"]) if sid in ("S2", "S14") else (A["up"], A["dn"])
        return run_f(df, side, em, sa, ent, flips, tf, ft, fr)
    if sid in TOP8_SID:                     # S22-S29
        c2, sg, sd, fs = TOP8_SID[sid]; df = getdf(c2); ft, fr = load_fund(c2)
        up, dn, _ = I.st_flips(df)
        return build_tr(c2, df, ft, fr, (up, dn), sg, sd, fs)
    if sid == "S30":                        # reversión a la media
        df = getdf("INJ"); ft, fr = load_fund("INJ"); c = df["close"]
        basis = c.rolling(20).mean(); dev = 2.0 * c.rolling(20).std(ddof=0)
        cond = (c < (basis - dev)) & (c > c.rolling(200).mean())
        ev = cond.values & ~np.roll(cond.values, 1); ev[0] = False
        return run_mr_local(df, +1, ev, c.rolling(20).mean().values, 3.0, 24, ft, fr)
    coin, sg, side, fs = LATE[sid]          # S31-S44
    df = getdf(coin); ft, fr = load_fund(coin); up, dn, _ = I.st_flips(df)
    le, se = SIGFN[sg](df); ev = np.asarray(le if side > 0 else se)
    fa = filt_arrays(df, side); mask = np.ones(len(df), bool)
    for f in fs:
        mask &= fa[f]
    return run_f(df, side, "atrstop", None, ev & mask, (up, dn), "1h", ft, fr)


def main():
    daily = {}; rows = []
    for s in STRAT.STRATEGIES:
        tr = tr_for(s.sid)
        if tr is None or len(tr) == 0:
            continue
        r = tr["ret"]; idx = tr["t_in"]; months = max((idx.max() - idx.min()).days / 30.44, 1)
        rows.append((s.sid, s.coin, "L" if s.side > 0 else "S", len(tr), len(tr) / months,
                     (r > 0).mean() * 100, r.mean() * 1e4))
        daily[s.sid] = tr.set_index("t_in")["ret"].resample("1D").sum()

    M = pd.concat(daily.values(), axis=1).fillna(0)
    sig = M.std().replace(0, np.nan); w = (1 / sig); w = (w / w.sum())
    port = (M * w.values).sum(axis=1)
    monthly = port.resample("ME").sum()
    eq = (1 + port).cumprod(); dd = (eq / eq.cummax() - 1).min()
    yrs = (M.index[-1] - M.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sharpe = port.mean() / port.std() * np.sqrt(365)
    tot_trmes = sum(r[4] for r in rows)

    print(f"\n{'='*70}\nRESUMEN — {len(rows)} estrategias activas")
    print(f"{'='*70}")
    longs = [r for r in rows if r[2] == "L"]; shorts = [r for r in rows if r[2] == "S"]
    print(f"Long: {len(longs)} · Short: {len(shorts)}")
    print(f"Trades/mes TOTAL (suma): {tot_trmes:.0f}")
    print(f"exp neto medio por trade: {np.mean([r[6] for r in rows]):.0f} bps (ya neto de ganancias y pérdidas)")
    print(f"WR medio: {np.mean([r[5] for r in rows]):.0f}%")
    print(f"\n--- PORTAFOLIO combinado (vol-parity 1/σ, 1× sin apalancar) ---")
    print(f"Rentabilidad MENSUAL media: {monthly.mean()*100:+.1f}%   (mediana {monthly.median()*100:+.1f}%)")
    print(f"Mejor mes {monthly.max()*100:+.0f}% · peor mes {monthly.min()*100:+.0f}% · meses+ {(monthly>0).mean()*100:.0f}%")
    print(f"CAGR {cagr*100:+.0f}% · maxDD {dd*100:.1f}% · Sharpe {sharpe:.2f}")
    print(f"\n--- proyección a $1,000 (1×) ---")
    print(f"  ~${monthly.mean()*1000:+.0f}/mes promedio")
    for lev, lbl in ((2.0, "2× (arranque prudente)"), (3.0, "3×")):
        mp = port * lev; mm = mp.resample("ME").sum(); eql = (1 + mp).cumprod()
        ddl = (eql / eql.cummax() - 1).min()
        print(f"  {lbl}: {mm.mean()*100:+.1f}%/mes (~${mm.mean()*1000:+.0f}) · maxDD {ddl*100:.0f}%")
    by = port.groupby(port.index.year).sum() * 100
    print(f"\nPor año (1×): " + " · ".join(f"{y}:{v:+.0f}%" for y, v in by.items()))


if __name__ == "__main__":
    main()
