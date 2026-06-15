"""Pipeline completo de alta convicción para monedas nuevas:
  Stage 1: templates del roster × filtros -> gate de calidad (exp>0, PF>=1.35, >=3/4 años, n>=40, funding).
  Stage 2: validación OOS de los candidatos (train23-24/test25-26 + sensibilidad).
  Salida: APROBADOS (suplentes de fiar) con correlación vs roster. NADA mediocre pasa.

Auto-detecta monedas nuevas (store menos las ya evaluadas). Uso: python pipeline_universo.py
"""
import os, glob
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\expandir_universo.py", encoding="utf-8").read()
exec(src.split("def main(")[0])   # templates, run_f, load_fund, detect_sweeps, recent, met, I, DATA, ROSTER_COINS

ALREADY = {"TRX", "XRP", "AVAX", "BTC", "SUI", "LTC", "ETH",   # roster
           "ADA", "BNB", "DOGE", "DOT", "LINK", "SOL"}          # ya evaluadas
FILTER_SETS = [[], ["trend"], ["sweep6"], ["trend", "vol"], ["sweep6", "trend"], ["regime", "trend"]]


def fil_arrays(df, side, sL, sS, ema_len=200, volwin=500, sweepF=6):
    c = df["close"]; _, _, regup, regdn = I.bx_parts(c)
    ema = c.ewm(span=ema_len, adjust=False).mean().values
    atrpct = (I.atr14(df) / c).values
    volmed = pd.Series(atrpct).rolling(volwin, min_periods=100).median().values
    return {"trend": (c.values > ema) if side > 0 else (c.values < ema), "vol": atrpct >= volmed,
            "sweep6": recent(sL if side > 0 else sS, sweepF),
            "regime": (np.asarray(regup) if side > 0 else np.asarray(regdn))}


def load_coin(coin):
    df = pd.read_parquet(DATA.format(c=coin, tf="1h")); df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("dt").sort_index()


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return met(None), met(None)
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


def run_one(coin, tname, filters, ema_len=200, W_=5, MAXAGE_=200, volwin=500, sweepF=6):
    df = load_coin(coin)
    global W, MAXAGE
    W, MAXAGE = W_, MAXAGE_
    sL, sS = detect_sweeps(df)
    T, flips = templates(coin, df); ft, fr = load_fund(coin)
    side, em, sa, entry = T[tname]
    fa = fil_arrays(df, side, sL, sS, ema_len, volwin, sweepF)
    mask = np.ones(len(df), bool)
    for f in filters:
        mask &= fa[f]
    return run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr)


def main():
    coins = sorted(os.path.basename(os.path.dirname(p)).replace("_USDT_USDT", "")
                   for p in glob.glob("D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/*/1h.parquet"))
    new = [c for c in coins if c not in ALREADY and os.path.exists(
        "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{}_USDT_USDT.parquet".format(c))]
    print(f"Monedas NUEVAS a evaluar: {len(new)} -> {new}\n")
    if not new:
        print("(aún no hay monedas nuevas descargadas)"); return

    # roster daily para correlación
    rd = []
    for coin in ROSTER_COINS:
        for tf in ("1h", "15m"):
            df = pd.read_parquet(DATA.format(c=coin, tf=tf)); df["dt"] = pd.to_datetime(df["ts"], unit="ms")
            df = df.set_index("dt").sort_index()
            ents, flips = roster_entries(coin, df); ft, fr = load_fund(coin)
            for sid, (side, em, sa, entry) in ents.items():
                if {"S3-TRX-L": "15m", "S7-AVAX-L": "15m"}.get(sid, "1h") != tf: continue
                tr = run_f(df, side, em, sa, entry, flips, tf, ft, fr)
                if tr is not None: rd.append(tr.set_index("t_in")["ret"].resample("1D").sum())
    R = pd.concat(rd, axis=1).fillna(0).sum(axis=1)

    # Stage 1: candidatos (precomputa arrays pesados 1 vez por moneda)
    cands = []
    for coin in new:
        df = load_coin(coin)
        global W, MAXAGE
        W, MAXAGE = 5, 200
        sL, sS = detect_sweeps(df)
        T, flips = templates(coin, df); ft, fr = load_fund(coin)
        fa_side = {+1: fil_arrays(df, +1, sL, sS), -1: fil_arrays(df, -1, sL, sS)}
        for tname, (side, em, sa, entry) in T.items():
            fa = fa_side[side]; best = None
            for fs in FILTER_SETS:
                mask = np.ones(len(df), bool)
                for f in fs:
                    mask &= fa[f]
                m = met(run_f(df, side, em, sa, entry & mask, flips, "1h", ft, fr))
                if not m or m["n"] < 40 or m["exp"] <= 0 or m["pf"] < 1.35 or m["ypos"] < m["ytot"] - 1:
                    continue
                if best is None or m["exp"] > best[1]["exp"]:
                    best = (fs, m)
            if best:
                cands.append((coin, tname, best[0]))
        print(f"  {coin}: {sum(1 for c in cands if c[0]==coin)} candidatos", flush=True)
    print(f"\nStage 1: {len(cands)} candidatos pasan el gate de calidad.\n")

    # Stage 2: validación OOS
    print(f"{'coin':6}{'template':12}{'filtros':16}{'full_exp':>9}{'PF':>6}{'test_exp':>9}{'sens':>14}{'corr':>7}  veredicto")
    approved = []
    for coin, tname, fs in cands:
        tr = run_one(coin, tname, fs); ff = met(tr)
        f_tr, f_te = split_met(tr)
        ex = []
        if "trend" in fs:
            for el in (150, 250): ex.append(met(run_one(coin, tname, fs, ema_len=el))["exp"] if run_one(coin, tname, fs, ema_len=el) is not None else -1)
        if any("sweep" in f for f in fs):
            for F in (3, 9, 12): ex.append((met(run_one(coin, tname, fs, sweepF=F)) or {"exp": -1})["exp"])
        if "vol" in fs:
            for vw in (300, 800): ex.append((met(run_one(coin, tname, fs, volwin=vw)) or {"exp": -1})["exp"])
        sens_ok = len(ex) == 0 or min(ex) > 0
        oos = f_tr["exp"] > 0 and f_te["exp"] > 0 and f_te["n"] >= 8
        v = "APROBADO" if (oos and sens_ok) else ("DUDOSO" if f_te["exp"] > 0 else "DESCARTADO")
        d = tr.set_index("t_in")["ret"].resample("1D").sum()
        corr = pd.concat([d, R], axis=1).fillna(0).corr().iloc[0, 1]
        srange = f"[{min(ex):.0f},{max(ex):.0f}]" if ex else "n/a"
        print(f"{coin:6}{tname:12}{('+'.join(fs) or 'base'):16}{ff['exp']:9.0f}{ff['pf']:6.2f}"
              f"{f_te['exp']:9.0f}{srange:>14}{corr:7.2f}  {v}")
        if v == "APROBADO":
            approved.append((coin, tname, fs, ff, corr))
    print(f"\n{'='*70}\nAPROBADOS (suplentes nuevos de fiar): {len(approved)}")
    for coin, tname, fs, ff, corr in sorted(approved, key=lambda x: x[3]["exp"], reverse=True):
        print(f"  {coin:6}{tname:12}{'+'.join(fs):16} exp={ff['exp']:.0f} PF={ff['pf']:.2f} corr_roster={corr:.2f}")


if __name__ == "__main__":
    main()
