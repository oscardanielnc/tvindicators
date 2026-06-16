"""Validación a fondo de la confluencia Squeeze[LazyBear]+MACD[ChrisMoody] en TRADFI (equity 1h).
Costos de equity REALES (5+4bp/lado, estándar conservador del proyecto — NO los cripto del POC).
Batería: anti-beta (vs random mismo-lado), long vs short, robustez por-ticker, OOS Sharpe + PSR.
Prueba las 3 variantes ganadoras del POC: C1/C2/C5. Uso: python validate_sqz_macd.py
"""
from __future__ import annotations
import sys, math
from statistics import NormalDist
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from poc_smc import load_equity, atr14, EQ
from poc_sqz_macd import build_signals

TAKER_E, SLIP_E = 0.0005, 0.0004        # costos equity-perp conservadores (= sweep_orb del proyecto)
TIMEOUT = 48
H = 48
IS_END = pd.Timestamp("2024-01-01", tz="UTC")
N01 = NormalDist(); RNG = np.random.RandomState(7)
COMBOS = ["C1_rel+macdDir", "C2_rel+histAccel", "C5_macdAbove+rel"]


def sim_sided(df, ent, side, atr):
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); rows = []; i = 5
    while i < n - 1:
        if not ent[i] or side[i] == 0:
            i += 1; continue
        s = int(side[i]); e = i + 1; epx = o[e]; stop = epx - s * 2 * atr[i]; exit_px = None
        for j in range(e, min(e + TIMEOUT, n)):
            if (s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop):
                exit_px = (min(o[j], stop) if s > 0 else max(o[j], stop)) * (1 - s * SLIP_E); co = TAKER_E + SLIP_E; break
        if exit_px is None:
            j = min(e + TIMEOUT, n - 1); exit_px = c[j]; co = TAKER_E
        rows.append((df.index[e], s, s * (exit_px / epx - 1) - TAKER_E - co)); i = j + 1
    return pd.DataFrame(rows, columns=["t", "side", "net"])


def random_baseline(df, nl, ns, reps=20):
    o, c = df["open"].values, df["close"].values; n = len(df)
    if n < H + 10:
        return np.nan
    L, S = [], []
    for _ in range(reps):
        idx = RNG.randint(5, n - H - 1, size=max(nl, ns, 1))
        fwd = c[idx + H] / o[idx + 1] - 1 - 2 * TAKER_E
        L.append(fwd[:nl].mean() if nl else 0); S.append((-fwd[:ns]).mean() if ns else 0)
    tot = nl + ns
    return (nl*np.mean(L) + ns*np.mean(S))/tot if tot else np.nan


def psr(net):
    net = np.asarray(net, float); T = len(net)
    if T < 5 or net.std(ddof=1) == 0:
        return np.nan
    sr = net.mean()/net.std(ddof=1); z = (net-net.mean())/net.std(ddof=1)
    sk = float((z**3).mean()); ku = float((z**4).mean())
    return N01.cdf((sr*math.sqrt(T-1))/math.sqrt(max(1e-12, 1 - sk*sr + ((ku-1)/4)*sr**2)))


def pf(x):
    x = np.asarray(x); return x[x > 0].sum()/max(-x[x < 0].sum(), 1e-9)


def validate_combo(name, per_sym_trades, base_by_sym):
    T = pd.concat(per_sym_trades.values(), ignore_index=True)
    if len(T) < 30:
        print(f"\n### {name}: pocos trades ({len(T)})"); return
    exp = T.net.mean()*1e4
    base = np.nansum([base_by_sym[s]*len(per_sym_trades[s]) for s in per_sym_trades]) / len(T)
    L, S = T[T.side > 0], T[T.side < 0]
    npos = sum(per_sym_trades[s].net.mean() > 0 for s in per_sym_trades)
    d = T.set_index("t")["net"].sort_index(); d.index = pd.to_datetime(d.index, utc=True)
    dd = d.resample("1D").sum(); oos = dd[dd.index >= IS_END]
    sh = oos.mean()/oos.std(ddof=1)*math.sqrt(252) if len(oos) > 2 and oos.std(ddof=1) > 0 else 0
    oexp = T[pd.to_datetime(T.t, utc=True) >= IS_END].net
    print(f"\n### {name}  (n={len(T)}, exp {exp:+.0f}bp, PF {pf(T.net.values):.2f})")
    print(f"  [anti-beta] exp {exp:+.0f}bp vs random mismo-lado {base:+.0f}bp -> alpha {exp-base:+.0f}bp "
          f"[{'★ timing' if exp-base > 5 else 'drift'}]")
    print(f"  [long/short] LONG n={len(L)} exp={L.net.mean()*1e4:+.0f}bp PF={pf(L.net.values):.2f} | "
          f"SHORT n={len(S)} exp={S.net.mean()*1e4:+.0f}bp PF={pf(S.net.values):.2f} "
          f"[{'★ ambos' if len(L) and len(S) and L.net.mean()>0 and S.net.mean()>0 else 'un lado falla'}]")
    print(f"  [robustez] {npos}/{len(per_sym_trades)} tickers exp>0")
    print(f"  [OOS] exp {oexp.mean()*1e4 if len(oexp) else 0:+.0f}bp · Sharpe diario {sh:+.2f} · PSR(0) {psr(oexp.values)*100:.0f}%")


def main():
    print(f"VALIDACIÓN Squeeze+MACD tradfi · costos equity {TAKER_E*1e4:.0f}+{SLIP_E*1e4:.0f}bp · "
          f"SL2xATR+to{TIMEOUT} · anti-beta H={H} · OOS>={IS_END.date()}")
    data = {}
    for cs in EQ:
        try:
            df = load_equity(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        data[cs] = (df, atr14(df), build_signals(df))
    for combo in COMBOS:
        per_sym = {}; base = {}
        for cs, (df, atr, S) in data.items():
            bull, bear = S[combo]
            ent = np.asarray(bull) | np.asarray(bear)
            side = np.where(np.asarray(bull), 1, np.where(np.asarray(bear), -1, 0)).astype(np.int8)
            t = sim_sided(df, ent, side, atr)
            if len(t) >= 5:
                per_sym[cs] = t
                base[cs] = random_baseline(df, int((t.side > 0).sum()), int((t.side < 0).sum()))
        validate_combo(combo, per_sym, base)


if __name__ == "__main__":
    main()
