"""POC — Candle Range Theory (CRT) en 4h. Patrón de 3 velas:
  A = rango [low, high].
  B = barre el rango de A con la MECHA pero cierra el CUERPO dentro (rechazo).
        - bullish: B.low < A.low y cuerpo de B dentro de [A.low, A.high]  -> rechazo alcista
        - bearish: B.high > A.high y cuerpo de B dentro de [A.low, A.high] -> rechazo bajista
  C = se ESPERA que se mueva en dirección del rechazo (entrada al open de C, salida al close de C).

Hipótesis del usuario. Mecánicamente = liquidity sweep + reversión (≈ ICT Turtle Soup, ya descartado).
Test honesto: expectancy NETA de costos > 0, PF>1.1, robusto IS/OOS y por dirección. Cripto: 1h->4h.
Desglose por hora-de-apertura de B (UTC) -> revela si la franja de apertura NY (~12:00 UTC) es especial.
Uso: python poc_crt.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

STORE = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"
TAKER, SLIP = 0.00045, 0.0002             # perp Binance: taker/lado + slippage (igual que el bot)
RT_COST = 2 * TAKER + 2 * SLIP            # round-trip (entrada open + salida close, conservador)
IS_END = pd.Timestamp("2024-01-01", tz="UTC")


def coins():
    base = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm"
    return sorted(os.path.basename(os.path.dirname(p)).replace("_USDT_USDT", "")
                  for p in glob.glob(base + "/*/1h.parquet"))


def load_4h(c):
    df = pd.read_parquet(STORE.format(c=c, tf="1h"))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("dt").sort_index()[["open", "high", "low", "close", "volume"]].astype(float)
    g = df.resample("4h").agg({"open": "first", "high": "max", "low": "min",
                               "close": "last", "volume": "sum"}).dropna()
    return g


def crt_trades(g, strict=True):
    """Devuelve DataFrame de trades CRT: una fila por triple (A,B,C) que forma patrón."""
    o, h, l, c = g["open"].values, g["high"].values, g["low"].values, g["close"].values
    idx = g.index
    rows = []
    for i in range(len(g) - 2):
        aL, aH = l[i], h[i]                       # rango de A
        if aH <= aL:
            continue
        bo, bc, bh, bl = o[i + 1], c[i + 1], h[i + 1], l[i + 1]
        body_lo, body_hi = min(bo, bc), max(bo, bc)
        body_in = (body_lo >= aL) and (body_hi <= aH)      # cuerpo de B dentro del rango de A
        side = 0
        if bl < aL and (bc > aL) and (not strict or body_in):
            side = +1                              # barrió low, cerró dentro -> rechazo alcista -> long C
        elif bh > aH and (bc < aH) and (not strict or body_in):
            side = -1                              # barrió high, cerró dentro -> rechazo bajista -> short C
        if side == 0:
            continue
        co, cc = o[i + 2], c[i + 2]                # vela C: entra al open, sale al close
        if co <= 0:
            continue
        gross = side * (cc / co - 1)
        rows.append((idx[i + 2], side, gross, gross - RT_COST, idx[i + 1].hour))
    return pd.DataFrame(rows, columns=["date", "side", "gross", "net", "b_hour"])


def stats(t):
    if len(t) < 20:
        return None
    net = t["net"].values
    wr = (net > 0).mean(); g = net[net > 0].sum(); ls = -net[net < 0].sum()
    pf = g / ls if ls > 0 else np.inf
    sd = net.std(ddof=1)
    return dict(n=len(t), wr=wr, exp=net.mean(), pf=pf,
                sharpe=net.mean() / sd * np.sqrt(len(t)) if sd > 0 else 0,
                cum=net.sum())


def show(tag, t):
    s = stats(t)
    if not s:
        print(f"  {tag:24} <20 trades"); return
    print(f"  {tag:24} n={s['n']:6} WR={s['wr']*100:4.1f}% exp={s['exp']*1e4:+6.1f}bp "
          f"PF={s['pf']:.3f} cum={s['cum']*100:+6.0f}%")


def main():
    cs = coins()
    print(f"CRT 4h · {len(cs)} monedas · costo round-trip {RT_COST*1e4:.1f}bp · IS<{IS_END.date()} OOS>=\n")
    allt = []
    for c in cs:
        try:
            t = crt_trades(load_4h(c))
            if len(t):
                t["coin"] = c; allt.append(t)
        except Exception as e:
            print(f"  (skip {c}: {e})")
    T = pd.concat(allt, ignore_index=True)
    T["seg"] = np.where(T["date"] < IS_END, "IS", "OOS")
    rng = (T["date"].min().date(), T["date"].max().date())
    print(f"Total triples-patrón: {len(T)} · rango {rng[0]}->{rng[1]}\n")

    print("===== POOL (todas las velas 4h, todas las horas) =====")
    show("TODOS", T); show("LONG (sweep low)", T[T.side == 1]); show("SHORT (sweep high)", T[T.side == -1])
    print("\n===== HOLDOUT IS / OOS =====")
    show("IS  todos", T[T.seg == "IS"]); show("OOS todos", T[T.seg == "OOS"])
    show("IS  long", T[(T.seg == "IS") & (T.side == 1)]); show("OOS long", T[(T.seg == "OOS") & (T.side == 1)])
    show("IS  short", T[(T.seg == "IS") & (T.side == -1)]); show("OOS short", T[(T.seg == "OOS") & (T.side == -1)])

    print("\n===== POR HORA DE APERTURA DE B (UTC) — ¿la franja de apertura NY (~12:00 UTC) es especial? =====")
    for hr in sorted(T["b_hour"].unique()):
        sub = T[T.b_hour == hr]
        mark = "  <- contiene apertura NY (09:30 ET=13:30 UTC EDT)" if hr == 12 else ""
        show(f"B abre {hr:02d}:00 UTC", sub)
        if mark:
            print(mark)

    print("\n===== Año a año (PnL neto sumado, todos) =====")
    by = T.assign(y=T["date"].dt.year).groupby("y")["net"]
    for y, v in by:
        print(f"  {y}: {v.sum()*100:+6.0f}%  (n={len(v)}, exp={v.mean()*1e4:+.1f}bp)")


if __name__ == "__main__":
    main()
