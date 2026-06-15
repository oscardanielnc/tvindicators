"""Tuneo de FILTROS de convicción para las 9 estrategias del roster.

Objetivo (Oscar 14/06): subir la CALIDAD de las entradas — no perder, alta convicción —
combinando filtros. Prioridad: todos los años positivos (no perder) + expectancy alta,
manteniendo frecuencia razonable. Reporta baseline vs MEJOR combinación por estrategia.

Filtros combinables (alineados al lado de cada estrategia):
  - sweep  : barrido de liquidez en las últimas F velas (F ∈ 3/6/12/24)
  - regime : línea de régimen B-Xtrender a favor
  - trend  : precio del lado correcto de la EMA200
  - vol    : ATR% por encima de su mediana móvil (evita chop muerto)

Reusa el motor de salida de poc_sweep_filter.py (paridad con engine.py).
Uso: python pulir_filtros.py
"""
import itertools
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_sweep_filter.py", encoding="utf-8").read()
exec(src.split("TFMAP =")[0])   # detect_sweeps, recent, roster_entries, run, I, DATA, WARM, etc.

TFMAP = {"S3-TRX-L": "15m", "S7-AVAX-L": "15m"}
COINS = ["TRX", "XRP", "AVAX", "BTC", "SUI", "LTC", "ETH"]
MINTR = {"1h": 40, "15m": 60}        # piso de frecuencia (calidad > cantidad, pero algo de freq)


def m2(tr):
    if tr is None or len(tr) == 0:
        return None
    r = tr["ret"]
    by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), wr=(r > 0).mean(), exp=r.mean() * 1e4,
                pf=r[r > 0].sum() / max(abs(r[r <= 0].sum()), 1e-9),
                ypos=int((by > 0).sum()), ytot=int(len(by)))


def filt_arrays(df, side, sL, sS):
    c = df["close"]
    green, red, regup, regdn = I.bx_parts(c)
    ema200 = c.ewm(span=200, adjust=False).mean().values
    atr = I.atr14(df).values
    atrpct = atr / c.values
    volmed = pd.Series(atrpct).rolling(500, min_periods=100).median().values
    return dict(
        regime=(regup if side > 0 else regdn),
        trend=(c.values > ema200) if side > 0 else (c.values < ema200),
        vol=atrpct >= volmed,
        sweep=(sL if side > 0 else sS),
    )


def main():
    summary = []
    for coin in COINS:
        for tf in ["1h", "15m"]:
            df = pd.read_parquet(DATA.format(c=coin, tf=tf))
            df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
            ents, flips = roster_entries(coin, df)
            sL, sS = detect_sweeps(df)
            for sid, (side, em, sa, entry) in ents.items():
                if TFMAP.get(sid, "1h") != tf:
                    continue
                fa = filt_arrays(df, side, sL, sS)
                base = m2(run(df, side, em, sa, entry, flips, tf))
                # grid de combinaciones
                best = None
                for F in (None, 3, 6, 12, 24):
                    sweep = fa["sweep"] if F is None else None
                    rec = recent(fa["sweep"], F) if F else None
                    for reg, tr_, vo in itertools.product((0, 1), (0, 1), (0, 1)):
                        mask = np.ones(len(df), bool)
                        tags = []
                        if F:
                            mask &= rec; tags.append(f"sweep≤{F}")
                        if reg:
                            mask &= fa["regime"]; tags.append("regime")
                        if tr_:
                            mask &= fa["trend"]; tags.append("trend")
                        if vo:
                            mask &= fa["vol"]; tags.append("vol")
                        if not tags:
                            continue
                        m = m2(run(df, side, em, sa, entry & mask, flips, tf))
                        if not m or m["n"] < MINTR[tf]:
                            continue
                        if m["ypos"] < m["ytot"]:          # exige TODOS los años positivos
                            continue
                        if best is None or m["exp"] > best[1]["exp"]:
                            best = (tags, m)
                summary.append((sid, tf, base, best))

    print(f"{'='*108}")
    print(f"{'estrat':10}{'tf':4} | {'BASELINE':^28} | {'MEJOR COMBO (todos años +, freq≥piso)':^48}")
    print(f"{'':10}{'':4} | {'WR  exp  PF   n  años':^28} | {'filtros':22}{'WR  exp  PF   n  años':^24}")
    print(f"{'-'*108}")
    for sid, tf, base, best in summary:
        b = f"{base['wr']*100:3.0f}% {base['exp']:5.0f} {base['pf']:4.2f} {base['n']:4} {base['ypos']}/{base['ytot']}"
        if best:
            tags, m = best
            bb = f"{m['wr']*100:3.0f}% {m['exp']:5.0f} {m['pf']:4.2f} {m['n']:4} {m['ypos']}/{m['ytot']}"
            tg = "+".join(tags)
            dwr = (m['wr'] - base['wr']) * 100
            dexp = m['exp'] - base['exp']
            print(f"{sid:10}{tf:4} | {b:^28} | {tg:22}{bb:^24}  (ΔWR{dwr:+.0f} Δexp{dexp:+.0f})")
        else:
            print(f"{sid:10}{tf:4} | {b:^28} | {'(ningún combo cumple el gate)':^48}")


if __name__ == "__main__":
    main()
