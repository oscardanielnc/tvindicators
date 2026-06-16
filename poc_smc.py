"""POC — Smart Money Concepts [LuxAlgo] portado (smc.py), evaluado STANDALONE en cripto + equities.
Prueba cada señal tradable como entrada (next-open), salida ATR-stop 2x + timeout, costos reales:
  BOS internal/swing (continuación), CHoCH internal/swing (reversión), OB retest, FVG, discount/premium.
Gate honesto: exp NETA>0 y PF>1.1, robusto IS/OOS. Prior fuerte: SMC en crudo ≈ patrones ya sin edge.
Uso: python poc_smc.py
"""
from __future__ import annotations
import os, sys, glob
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import smc

TAKER, SLIP = 0.00045, 0.0002
CSTORE = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/1h.parquet"
ESTORE = "D:/OSCAR/Documents/Trading Proyects/tvindicators/tradfi/data_db/{c}_1m.parquet"
IS_END_C = pd.Timestamp("2024-09-01", tz="UTC")     # cripto store ~2022-06..2026-06 -> ~70/30
IS_END_E = pd.Timestamp("2024-01-01", tz="UTC")
CRYPTO = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AVAX", "LINK", "LTC", "ADA",
          "ARB", "OP", "INJ", "SUI", "NEAR", "DOT", "ATOM", "FET"]
EQ = ["AAPL", "NVDA", "TSLA", "AMD", "MU", "AAL", "JPM", "XOM"]
TIMEOUT_BARS = 48


def load_crypto(c):
    df = pd.read_parquet(CSTORE.format(c=c)); df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt").sort_index()[["open", "high", "low", "close", "volume"]].astype(float)


def load_equity(c):
    df = pd.read_parquet(ESTORE.format(c=c))
    idx = pd.to_datetime(df.index); idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df = df[["open", "high", "low", "close", "volume"]].astype(float); df.index = idx
    return df.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()


def atr14(df):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values


def sim(df, entry, side_arr, atr, timeout=TIMEOUT_BARS):
    """entry bool array; side_arr int (+1/-1) por barra (o escalar). Entrada next-open, SL 2xATR, timeout."""
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    n = len(df); trades = []
    i = 5
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        side = side_arr if np.isscalar(side_arr) else side_arr[i]
        if side == 0:
            i += 1; continue
        e = i + 1; epx = o[e]; stop = epx - side * 2 * atr[i]
        exit_px = None
        for j in range(e, min(e + timeout, n)):
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exit_px = (min(o[j], stop) if side > 0 else max(o[j], stop)) * (1 - side * SLIP)
                co = TAKER + SLIP; break
        if exit_px is None:
            j = min(e + timeout, n - 1); exit_px = c[j]; co = TAKER
        net = side * (exit_px / epx - 1) - TAKER - co
        trades.append((df.index[e], net)); i = j + 1
    return pd.DataFrame(trades, columns=["t", "net"]) if trades else pd.DataFrame(columns=["t", "net"])


def ob_retest_entries(df, res, internal):
    """Marca barras donde el precio re-entra en un OB activo (en dirección del bias)."""
    n = len(df); ent = np.zeros(n, bool); side = np.zeros(n, np.int8)
    h, l = df["high"].values, df["low"].values
    for ob in res["obs"]:
        if ob["internal"] != internal:
            continue
        for j in range(ob["created"] + 1, min(ob["created"] + 200, n)):
            # mitigación: si lo violan, parar
            if ob["bias"] == smc.BULL and l[j] < ob["low"]:
                break
            if ob["bias"] == smc.BEAR and h[j] > ob["high"]:
                break
            in_zone = (l[j] <= ob["high"] and h[j] >= ob["low"])
            if in_zone:
                ent[j] = True; side[j] = ob["bias"]; break
    return ent, side


def evaluate(name, loader, syms, is_end):
    print(f"\n{'#'*92}\n# {name}  ({len(syms)} símbolos)\n{'#'*92}")
    agg = {}
    for c in syms:
        try:
            df = loader(c)
        except Exception as e:
            print(f"  (skip {c}: {str(e)[:50]})"); continue
        if len(df) < 600:
            continue
        res = smc.compute(df)
        atr = atr14(df)
        sigs = {
            "iBOS": (res["ibos_bull"], res["ibos_bear"]),
            "iCHoCH": (res["ichoch_bull"], res["ichoch_bear"]),
            "sBOS": (res["sbos_bull"], res["sbos_bear"]),
            "sCHoCH": (res["schoch_bull"], res["schoch_bear"]),
            "FVG": (res["fvg_bull"], res["fvg_bear"]),
        }
        for nm, (bull, bear) in sigs.items():
            ent = bull | bear
            side = np.where(bull, 1, np.where(bear, -1, 0)).astype(np.int8)
            t = sim(df, ent, side, atr)
            agg.setdefault(nm, []).append(t)
        # OB retest (internal + swing)
        for tag, internal in (("OB_int", True), ("OB_swing", False)):
            ent, side = ob_retest_entries(df, res, internal)
            agg.setdefault(tag, []).append(sim(df, ent, side, atr))
        # discount-long / premium-short (evento al entrar en zona)
        disc, prem = res["discount"], res["premium"]
        disc_ev = disc & ~np.r_[False, disc[:-1]]
        prem_ev = prem & ~np.r_[False, prem[:-1]]
        ent = disc_ev | prem_ev; side = np.where(disc_ev, 1, np.where(prem_ev, -1, 0)).astype(np.int8)
        agg.setdefault("Zone(disc-L/prem-S)", []).append(sim(df, ent, side, atr))

    print(f"  {'señal':22} {'n':>6} {'WR':>5} {'exp':>8} {'PF':>6}   {'OOS n':>6} {'OOS exp':>8} {'OOS PF':>6}")
    for nm, lst in agg.items():
        T = pd.concat(lst, ignore_index=True)
        if len(T) < 20:
            print(f"  {nm:22} {len(T):>6}  <20"); continue
        oos = T[T["t"] >= is_end]
        def m(x):
            if len(x) < 5:
                return (len(x), np.nan, np.nan, np.nan)
            net = x["net"].values; pf = net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9)
            return (len(x), (net > 0).mean()*100, net.mean()*1e4, pf)
        n_, wr, exp, pf = m(T); on, _, oexp, opf = m(oos)
        star = "★" if (exp > 0 and pf > 1.15 and not np.isnan(oexp) and oexp > 0 and opf > 1.1) else " "
        print(f" {star}{nm:22} {n_:>6} {wr:>4.0f}% {exp:>+7.0f}bp {pf:>6.2f}   {on:>6} {oexp:>+7.0f}bp {opf:>6.2f}")


def main():
    print("SMC [LuxAlgo] STANDALONE · entrada next-open · SL 2xATR + timeout 48 · "
          f"costos {TAKER*1e4:.0f}bp/lado+{SLIP*1e4:.0f}slip · ★=exp>0&PF>1.15 en total Y OOS")
    evaluate("CRIPTO 1h", load_crypto, CRYPTO, IS_END_C)
    evaluate("EQUITIES 1h", load_equity, EQ, IS_END_E)


if __name__ == "__main__":
    main()
