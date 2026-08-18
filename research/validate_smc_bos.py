"""Validación a fondo del Swing Break of Structure (sBOS) de SMC [LuxAlgo].
Pruebas que matan falsos edges:
  1) ANTI-BETA: ¿sBOS supera a entradas RANDOM del mismo lado y mismo horizonte? (timing vs drift)
  2) LONG vs SHORT por separado: si los shorts también ganan, NO es beta long de un mercado alcista.
  3) ROBUSTEZ por símbolo: % de símbolos con exp>0 (que no lo carguen 1-2).
  4) HOLDOUT IS/OOS + Sharpe diario pooled + PSR(0).
Reusa smc.compute y los loaders de poc_smc. Uso: python validate_smc_bos.py
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

import smc
from poc_smc import load_crypto, load_equity, atr14, CRYPTO, EQ, TAKER, SLIP, TIMEOUT_BARS

N01 = NormalDist()
RNG = np.random.RandomState(42)
H = 48                       # horizonte fijo para el test de timing (anti-beta), en barras


def sbos_trades(df, atr):
    """Trades sBOS reales (SL 2xATR + timeout). Devuelve DataFrame t,side,net."""
    res = smc.compute(df)
    bull, bear = res["sbos_bull"], res["sbos_bear"]
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); rows = []; i = 5
    while i < n - 1:
        side = 1 if bull[i] else (-1 if bear[i] else 0)
        if side == 0:
            i += 1; continue
        e = i + 1; epx = o[e]; stop = epx - side * 2 * atr[i]; exit_px = None
        for j in range(e, min(e + TIMEOUT_BARS, n)):
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exit_px = (min(o[j], stop) if side > 0 else max(o[j], stop)) * (1 - side * SLIP)
                co = TAKER + SLIP; break
        if exit_px is None:
            j = min(e + TIMEOUT_BARS, n - 1); exit_px = c[j]; co = TAKER
        net = side * (exit_px / epx - 1) - TAKER - co
        rows.append((df.index[e], side, net)); i = j + 1
    return pd.DataFrame(rows, columns=["t", "side", "net"])


def random_same_side_baseline(df, n_long, n_short, reps=20):
    """Entrada RANDOM, horizonte fijo H, neto de costos. Devuelve exp medio ponderado al mix long/short."""
    o, c = df["open"].values, df["close"].values
    n = len(df)
    if n < H + 10:
        return np.nan
    longs, shorts = [], []
    for _ in range(reps):
        idx = RNG.randint(5, n - H - 1, size=max(n_long, n_short, 1))
        fwd = c[idx + H] / o[idx + 1] - 1 - 2 * TAKER
        longs.append(fwd[:n_long].mean() if n_long else 0)
        shorts.append((-fwd[:n_short]).mean() if n_short else 0)
    el, es = np.mean(longs), np.mean(shorts)
    tot = n_long + n_short
    return (n_long * el + n_short * es) / tot if tot else np.nan


def psr(net):
    net = np.asarray(net, float); T = len(net)
    if T < 5:
        return np.nan
    sd = net.std(ddof=1)
    if sd == 0:
        return np.nan
    sr = net.mean() / sd; z = (net - net.mean()) / sd
    sk = float((z**3).mean()); ku = float((z**4).mean())
    den = math.sqrt(max(1e-12, 1 - sk*sr + ((ku-1)/4)*sr**2))
    return N01.cdf((sr*math.sqrt(T-1))/den)


def daily_sharpe(t, is_end):
    s = t.set_index("t")["net"].sort_index()
    d = s.resample("1D").sum()
    oos = d[d.index >= is_end]
    def sh(x): return x.mean()/x.std(ddof=1)*math.sqrt(365) if len(x) > 2 and x.std(ddof=1) > 0 else 0
    return sh(d), sh(oos), oos


def run(name, loader, syms, is_end):
    print(f"\n{'='*94}\n{name}\n{'='*94}")
    per_sym = []; allt = []
    for cs in syms:
        try:
            df = loader(cs)
        except Exception as e:
            print(f"  skip {cs}: {str(e)[:40]}"); continue
        if len(df) < 600:
            continue
        atr = atr14(df)
        t = sbos_trades(df, atr)
        if len(t) < 10:
            continue
        t["sym"] = cs; allt.append(t)
        nl, ns = int((t.side > 0).sum()), int((t.side < 0).sum())
        base = random_same_side_baseline(df, nl, ns)
        exp = t["net"].mean()
        per_sym.append(dict(sym=cs, n=len(t), exp_bp=exp*1e4, base_bp=base*1e4,
                            alpha_bp=(exp-base)*1e4, pf=t.net[t.net>0].sum()/max(-t.net[t.net<0].sum(),1e-9),
                            nl=nl, ns=ns,
                            expL=t.net[t.side>0].mean()*1e4 if nl else np.nan,
                            expS=t.net[t.side<0].mean()*1e4 if ns else np.nan))
    T = pd.concat(allt, ignore_index=True)
    P = pd.DataFrame(per_sym)

    # 1) anti-beta agregado
    exp = T.net.mean()*1e4
    base = np.nansum(P.base_bp*P.n)/P.n.sum()
    print(f"\n[1] ANTI-BETA (timing vs drift): sBOS exp {exp:+.0f}bp/trade  vs  random mismo-lado {base:+.0f}bp  "
          f"-> ALPHA de timing {exp-base:+.0f}bp  [{'★ timing real' if exp-base>5 else 'es drift, NO timing'}]")

    # 2) long vs short
    L, S = T[T.side>0], T[T.side<0]
    print(f"[2] LONG vs SHORT:  LONG n={len(L)} exp={L.net.mean()*1e4:+.0f}bp PF={L.net[L.net>0].sum()/max(-L.net[L.net<0].sum(),1e-9):.2f}  | "
          f"SHORT n={len(S)} exp={S.net.mean()*1e4:+.0f}bp PF={S.net[S.net>0].sum()/max(-S.net[S.net<0].sum(),1e-9):.2f}  "
          f"[{'★ ambos lados ganan = no es beta' if (len(L) and len(S) and L.net.mean()>0 and S.net.mean()>0) else 'un lado falla'}]")

    # 3) robustez por símbolo
    pos = (P.exp_bp > 0).sum(); posa = (P.alpha_bp > 0).sum()
    print(f"[3] ROBUSTEZ: {pos}/{len(P)} símbolos exp>0 · {posa}/{len(P)} con alpha>0 (vs random)")
    print(f"    top: " + " ".join(f"{r.sym}({r.exp_bp:+.0f})" for _, r in P.sort_values('exp_bp',ascending=False).head(5).iterrows()))
    print(f"    bot: " + " ".join(f"{r.sym}({r.exp_bp:+.0f})" for _, r in P.sort_values('exp_bp').head(5).iterrows()))

    # 4) holdout + sharpe + PSR
    sh_all, sh_oos, oos = daily_sharpe(T, is_end)
    print(f"[4] Sharpe diario (pooled): total {sh_all:+.2f} · OOS {sh_oos:+.2f} · "
          f"PSR(0) OOS {psr(oos.values)*100:.0f}% · OOS exp {oos.mean()*1e4 if len(oos) else 0:+.1f}bp/día")
    return P


def main():
    print(f"VALIDACIÓN sBOS · SL 2xATR+timeout{TIMEOUT_BARS} · costos {TAKER*1e4:.0f}+{SLIP*1e4:.0f}bp · "
          f"anti-beta horizonte {H} barras")
    run("CRIPTO 1h", load_crypto, CRYPTO, pd.Timestamp("2024-09-01", tz="UTC"))
    run("EQUITIES 1h", load_equity, EQ, pd.Timestamp("2024-01-01", tz="UTC"))


if __name__ == "__main__":
    main()
