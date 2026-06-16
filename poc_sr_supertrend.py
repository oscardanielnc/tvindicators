"""POC — S/R Levels with Breaks [LuxAlgo] + Supertrend, solos y COMBINADOS, cripto + tradfi.
Supertrend (ATR10x3) YA está en el bot (I.st_flips). S/R-break LuxAlgo se porta aquí: pivotes 15/15,
ruptura confirmada por oscilador de volumen (EMA5 vs EMA10 > thr) + filtro de mecha.
Tesis del usuario: brillan COMBINADOS en tradfi (ruptura S/R en dirección de la tendencia Supertrend).
Incluye anti-beta POR TICKER (lección Squeeze+MACD). Uso: python poc_sr_supertrend.py
"""
from __future__ import annotations
import sys, math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from poc_smc import load_crypto, load_equity, atr14, sim, CRYPTO, EQ, TAKER, SLIP, TIMEOUT_BARS
from tvbot import indicators as I

IS_C = pd.Timestamp("2024-09-01", tz="UTC")
IS_E = pd.Timestamp("2024-01-01", tz="UTC")
H = 48
RNG = np.random.RandomState(11)


def sr_break(df, left=15, right=15, vol_thr=20.0):
    """Port LuxAlgo S/R with Breaks. Devuelve (brkL, brkS) eventos de ruptura con volumen + mecha."""
    h, l, c, o, v = (df[x].values for x in ("high", "low", "close", "open", "volume"))
    n = len(df)
    # pivots centrados (confirmados con 'right' barras de retraso), nivel ffill
    res = np.full(n, np.nan); sup = np.full(n, np.nan)
    for i in range(left, n - right):
        win_h = h[i-left:i+right+1]; win_l = l[i-left:i+right+1]
        if h[i] == win_h.max() and np.argmax(win_h) == left:
            res[i] = h[i]
        if l[i] == win_l.min() and np.argmin(win_l) == left:
            sup[i] = l[i]
    # nivel disponible recién en i+right (+1), luego ffill (= fixnan(pivot[1]) con offset)
    resLvl = np.full(n, np.nan); supLvl = np.full(n, np.nan)
    last_r = np.nan; last_s = np.nan
    for i in range(n):
        j = i - right - 1
        if j >= 0:
            if not np.isnan(res[j]):
                last_r = res[j]
            if not np.isnan(sup[j]):
                last_s = sup[j]
        resLvl[i] = last_r; supLvl[i] = last_s
    short = pd.Series(v).ewm(span=5, adjust=False).mean().values
    long = pd.Series(v).ewm(span=10, adjust=False).mean().values
    osc = 100 * (short - long) / np.where(long == 0, np.nan, long)
    cu = (c < resLvl) ; xover = (~cu) & np.r_[True, cu[:-1]]                 # crossover close>res
    cd = (c > supLvl) ; xunder = (~cd) & np.r_[True, cd[:-1]]               # crossunder close<sup
    body_up = (o - l) <= (c - o)        # not(open-low > close-open): mecha inferior <= cuerpo
    body_dn = (o - c) >= (high_open := (h - o))    # not(open-close < high-open)
    brkL = xover & ~np.isnan(resLvl) & body_up & (osc > vol_thr)
    brkS = xunder & ~np.isnan(supLvl) & body_dn & (osc > vol_thr)
    return brkL, brkS


def signals(df):
    brkL, brkS = sr_break(df)
    up, dn, sd = I.st_flips(df)                       # sd = dirección de tendencia Supertrend (1/-1)
    sd = np.asarray(sd)
    stflipL = np.asarray(up); stflipS = np.asarray(dn)
    trend_up = sd == 1; trend_dn = sd == -1
    return {
        "SR_break":     (brkL, brkS),
        "ST_flip":      (stflipL, stflipS),
        "SR+ST_trend":  (brkL & trend_up, brkS & trend_dn),       # ruptura en dirección de la tendencia ST
        "ST_flip+SRrec": (stflipL & pd.Series(brkL).rolling(10, min_periods=1).max().astype(bool).values,
                          stflipS & pd.Series(brkS).rolling(10, min_periods=1).max().astype(bool).values),
    }


def stats(T, is_end):
    if len(T) < 15:
        return None
    T = T.copy(); T["t"] = pd.to_datetime(T["t"], utc=True)
    net = T["net"].values; pf = net[net > 0].sum()/max(-net[net < 0].sum(), 1e-9)
    oos = T[T["t"] >= is_end]["net"].values
    return dict(n=len(T), exp=net.mean()*1e4, pf=pf,
                oexp=oos.mean()*1e4 if len(oos) >= 5 else np.nan,
                opf=(oos[oos > 0].sum()/max(-oos[oos < 0].sum(), 1e-9)) if len(oos) >= 5 else np.nan)


def evaluate(name, loader, syms, is_end):
    print(f"\n{'#'*86}\n# {name}\n{'#'*86}")
    agg = {}
    for cs in syms:
        try:
            df = loader(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        atr = atr14(df); S = signals(df)
        for nm, (bull, bear) in S.items():
            ent = np.asarray(bull) | np.asarray(bear)
            side = np.where(np.asarray(bull), 1, np.where(np.asarray(bear), -1, 0)).astype(np.int8)
            agg.setdefault(nm, []).append(sim(df, ent, side, atr))
    print(f"  {'señal':16} {'n':>6} {'exp':>8} {'PF':>6}   {'OOS exp':>8} {'OOS PF':>6}")
    for nm, lst in agg.items():
        s = stats(pd.concat(lst, ignore_index=True), is_end)
        if s is None:
            print(f"  {nm:16} <15"); continue
        star = "★" if (s["exp"] > 0 and s["pf"] > 1.15 and not np.isnan(s["oexp"]) and s["oexp"] > 0 and s["opf"] > 1.1) else " "
        print(f" {star}{nm:16} {s['n']:>6} {s['exp']:>+7.0f}bp {s['pf']:>6.2f}   {s['oexp']:>+7.0f}bp {s['opf']:>6.2f}")


def antibeta_equity(combo="SR+ST_trend"):
    """Anti-beta POR TICKER del combo estrella en equity (la prueba que distingue alpha de beta)."""
    print(f"\n{'='*86}\nANTI-BETA POR TICKER (equity, {combo}) — ¿timing o beta?\n{'='*86}")
    allt = []
    for cs in EQ:
        try:
            df = load_equity(cs)
        except Exception:
            continue
        if len(df) < 600:
            continue
        atr = atr14(df); bull, bear = signals(df)[combo]
        ent = np.asarray(bull) | np.asarray(bear)
        side = np.where(np.asarray(bull), 1, np.where(np.asarray(bear), -1, 0)).astype(np.int8)
        t = sim(df, ent, side, atr)
        if len(t) < 10:
            continue
        L = int(np.sum((side == 1) & ent)); Sx = int(np.sum((side == -1) & ent))
        o, c = df["open"].values, df["close"].values; n = len(df)
        rb = []
        for k in range(20):
            idx = np.random.RandomState(k).randint(5, n - H - 1, size=max(L, Sx, 1))
            fwd = c[idx + H]/o[idx + 1] - 1 - 2*TAKER
            rb.append((L*fwd[:L].mean() if L else 0) + (Sx*(-fwd[:Sx]).mean() if Sx else 0))
        base = (np.mean(rb)/(L+Sx))*1e4 if (L+Sx) else np.nan
        exp = t.net.mean()*1e4
        allt.append(dict(sym=cs, n=len(t), exp=exp, base=base, alpha=exp-base,
                         pf=t.net[t.net > 0].sum()/max(-t.net[t.net < 0].sum(), 1e-9), L=L, S=Sx,
                         pos=exp > 0, apos=exp-base > 5))
        print(f"  {cs:5} n={len(t):4} exp={exp:+5.0f}bp PF={allt[-1]['pf']:.2f}  "
              f"randomMix={base:+.0f}bp  alpha={exp-base:+.0f}bp  (L={L} S={Sx})")
    if allt:
        P = pd.DataFrame(allt)
        print(f"\n  RESUMEN: {P.pos.sum()}/{len(P)} tickers exp>0 · {P.apos.sum()}/{len(P)} con alpha>0 (timing) · "
              f"exp medio {P.exp.mean():+.0f}bp · alpha medio {P.alpha.mean():+.0f}bp")
        print(f"  -> {'★ TIMING real (alpha amplio)' if P.apos.sum() >= 0.6*len(P) and P.alpha.mean() > 5 else 'es BETA (alpha desaparece) -> NO promover'}")


def main():
    print("S/R Breaks[LuxAlgo] + Supertrend · solos y combinados · SL2xATR+to48 · ★=exp>0&PF>1.15 total Y OOS")
    evaluate("CRIPTO 1h", load_crypto, CRYPTO, IS_C)
    evaluate("EQUITIES 1h", load_equity, EQ, IS_E)
    antibeta_equity("SR+ST_trend")


if __name__ == "__main__":
    main()
