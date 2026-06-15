"""Replica honesta de la estrategia del stream 'Forex Education Live' (S/D 1m, BTC/ETH).

Modelo inferido de 5 capturas en vivo (14/06/2026):
  - TREND (pendiente de EMA) = filtro maestro.
  - Entrada = ruptura de micro-rango a favor de tendencia (momentum). RSI = cosmetico.
  - TP del stream = zona opuesta (banda de extremos recientes). T1 borde cercano / T2 lejano.
  - SL del stream = NINGUNO -> por eso el win rate alto es supervivencia (perdedores no se marcan).

Aqui medimos lo que el stream NO muestra: MAE (cuanto se va en contra), y barremos SL/TP
para hallar si hay edge REAL en la entrada y cual seria el stop ideal. Costos taker reales,
banda intrabar optimista/pesimista. Research standalone (Fase 1) -- no toca el bot vivo.

v2: generalizado a cualquier TF, entrada por EVENTO + cooldown, exits en multiplos de ATR.
"""
import numpy as np
import pandas as pd

from tvbot import indicators as I   # pine_ema, atr14 (replicas Pine ya validadas)

OHLCV = "C:/Users/LENOVO/Oscilion/data/ohlcv/binanceusdm/{c}_USDT_USDT/{tf}.parquet"


# ---------------------------------------------------------------- datos
def load(coin, tf="1m"):
    df = pd.read_parquet(OHLCV.format(c=coin, tf=tf))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("dt").sort_index()


# ---------------------------------------------------------------- componentes
def trend_state(close, n=50):
    """+1 up / -1 down / 0 neutral, segun precio vs EMA(n) y pendiente de la EMA."""
    ema = I.pine_ema(close, n)
    slope = ema.diff().values
    up = (close.values > ema.values) & (slope > 0)
    dn = (close.values < ema.values) & (slope < 0)
    return np.where(up, 1, np.where(dn, -1, 0))


def zones(df, look=90):
    """Zonas S/D = bandas de extremos recientes (los TP del stream).
    hi = resistencia/oferta, lo = soporte/demanda. shift(1) => sin look-ahead."""
    hi = df["high"].rolling(look).max().shift(1).values
    lo = df["low"].rolling(look).min().shift(1).values
    return hi, lo


def entries(df, trend_len=50, entry_look=10, event=False):
    """Ruptura de micro-rango a favor de tendencia.
    long = TREND up y close rompe el maximo de las ultimas entry_look velas. short = espejo.
    event=True => dispara SOLO en la vela que cruza (no en cada vela del estado) -> selectivo."""
    c = df["close"]
    tr = trend_state(c, trend_len)
    hh = df["high"].rolling(entry_look).max().shift(1).values
    ll = df["low"].rolling(entry_look).min().shift(1).values
    longs = (tr == 1) & (c.values > hh)
    shorts = (tr == -1) & (c.values < ll)
    if event:
        longs = longs & ~np.r_[False, longs[:-1]]
        shorts = shorts & ~np.r_[False, shorts[:-1]]
    return longs, shorts, tr


# ---------------------------------------------------------------- motor de backtest
def backtest(df, longs, shorts, tp_pct=None, sl_pct=None, hi=None, lo=None,
             atr=None, tp_atr=None, sl_atr=None, cooldown=0,
             timeout=240, fee=0.00045, slip=0.0002, one_at_a_time=True):
    """Backtest secuencial (1 posicion a la vez). Entrada al OPEN de la vela siguiente.

    Exit: TP por ATR (tp_atr) / fijo % (tp_pct) / zona opuesta (hi/lo); SL por ATR (sl_atr) /
    fijo % (sl_pct) / ninguno; timeout por #velas; cooldown = #velas de espera tras cada salida.
    Devuelve 2 retornos por trade: optimista (vela toca TP y SL -> asume TP) y pesimista
    (asume SL) = banda intrabar. MAE/MFE en % ajustado al lado.
    """
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    n = len(c); rt = 2 * (fee + slip)   # costo ida y vuelta
    rows = []
    i = 0
    while i < n - 1:
        side = 1 if longs[i] else (-1 if shorts[i] else 0)
        if side == 0:
            i += 1
            continue
        e = i + 1
        entry = o[e]
        if not np.isfinite(entry) or entry <= 0:
            i += 1
            continue
        # objetivo TP/SL: ATR, fijo %, o zona opuesta
        if tp_atr is not None:
            tp_lvl = entry + side * tp_atr * atr[i]
        elif tp_pct is not None:
            tp_lvl = entry * (1 + side * tp_pct)
        else:
            tp_lvl = hi[i] if side > 0 else lo[i]      # zona opuesta vigente en la entrada
        if sl_atr is not None:
            sl_lvl = entry - side * sl_atr * atr[i]
        elif sl_pct is not None:
            sl_lvl = entry * (1 - side * sl_pct)
        else:
            sl_lvl = None
        if not np.isfinite(tp_lvl):
            i += 1
            continue
        end = min(e + timeout, n - 1)

        mae = 0.0; mfe = 0.0; reason = "time"; jx = end
        exit_opt = exit_pess = c[end]
        for j in range(e, end + 1):
            fav = side * (h[j] - entry) / entry if side > 0 else side * (l[j] - entry) / entry
            adv = side * (l[j] - entry) / entry if side > 0 else side * (h[j] - entry) / entry
            if fav > mfe:
                mfe = fav
            if adv < mae:
                mae = adv
            tp_hit = (h[j] >= tp_lvl) if side > 0 else (l[j] <= tp_lvl)
            sl_hit = (sl_lvl is not None) and ((l[j] <= sl_lvl) if side > 0 else (h[j] >= sl_lvl))
            if tp_hit and sl_hit:
                exit_opt, exit_pess, reason, jx = tp_lvl, sl_lvl, "ambig", j
                break
            if tp_hit:
                exit_opt = exit_pess = tp_lvl; reason = "tp"; jx = j; break
            if sl_hit:
                exit_opt = exit_pess = sl_lvl; reason = "sl"; jx = j; break

        ret_opt = side * (exit_opt - entry) / entry - rt
        ret_pess = side * (exit_pess - entry) / entry - rt
        rows.append((df.index[e], side, entry, df.index[jx], reason,
                     ret_opt, ret_pess, mfe, -mae, jx - e + 1))
        i = (jx + 1 + cooldown) if one_at_a_time else i + 1

    return pd.DataFrame(rows, columns=[
        "t_in", "side", "entry", "t_out", "reason",
        "ret_opt", "ret_pess", "mfe", "mae", "bars"])


def signal_mae(df, longs, shorts, fav_thresh=0.002, timeout=240):
    """Para CADA senal cruda: cuanto se va EN CONTRA (MAE) antes de alcanzar fav_thresh a
    favor, o hasta timeout. Responde el '1/5 vs 1/2' del usuario."""
    h = df["high"].values; l = df["low"].values; o = df["open"].values; n = len(o)
    sig = np.where(longs, 1, np.where(shorts, -1, 0))
    idx = np.flatnonzero(sig != 0)
    out = []
    for i in idx:
        e = i + 1
        if e >= n:
            continue
        side = sig[i]; entry = o[e]
        end = min(e + timeout, n - 1)
        mae = 0.0; reached = False; bars_to_fav = np.nan
        for j in range(e, end + 1):
            adv = side * (l[j] - entry) / entry if side > 0 else side * (h[j] - entry) / entry
            fav = side * (h[j] - entry) / entry if side > 0 else side * (l[j] - entry) / entry
            if adv < mae:
                mae = adv
            if fav >= fav_thresh:
                reached = True; bars_to_fav = j - e + 1; break
        out.append((side, -mae, reached, bars_to_fav))
    return pd.DataFrame(out, columns=["side", "mae_before_fav", "reached_fav", "bars_to_fav"])


# ---------------------------------------------------------------- metricas
def metrics(tr, col="ret_pess"):
    if tr is None or len(tr) == 0:
        return None
    r = tr[col].values
    wins = r[r > 0]; losses = r[r <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf
    return {
        "n": len(r),
        "wr": (r > 0).mean(),
        "exp_bps": r.mean() * 1e4,                 # expectancy en bps de nominal
        "pf": pf,
        "total_pct": r.sum() * 100,
        "avg_win_bps": wins.mean() * 1e4 if len(wins) else 0,
        "avg_loss_bps": losses.mean() * 1e4 if len(losses) else 0,
        "worst5_bps": np.sort(r)[:5] * 1e4,
        "med_bars": tr["bars"].median(),
    }


def fmt(m):
    if not m:
        return "sin trades"
    return (f"n={m['n']:5d}  WR={m['wr']*100:4.1f}%  exp={m['exp_bps']:+6.1f}bps  "
            f"PF={m['pf']:4.2f}  tot={m['total_pct']:+7.1f}%  "
            f"win={m['avg_win_bps']:+5.1f} loss={m['avg_loss_bps']:+6.1f}  "
            f"peor5={np.round(m['worst5_bps'],0)}")
