"""Validación a fondo de los 4 combos de filtros prometedores (S1, S6, S8, S4).

Tres pruebas para separar señal real de sobreajuste:
  1) FUNDING REAL incluido (el tuneo lo omitió) — metrics honestos baseline vs filtrado.
  2) OOS ciego: train (2023-2024) vs test (2025-2026). El filtro debe ayudar en AMBOS,
     no solo en el periodo donde se eligió.
  3) SENSIBILIDAD: perturbar los knobs del filtro (F del sweep, largo EMA tendencia,
     W/MAXAGE del detector de barridos). Si el edge solo vive en el valor exacto = frágil.

Reusa el motor de salida de poc_sweep_filter.py + funding (paridad engine.py / portafolio.py).
Uso: python validar_combos.py
"""
import numpy as np
import pandas as pd

src = open(r"D:\OSCAR\Documents\Trading Proyects\tvindicators\poc_sweep_filter.py", encoding="utf-8").read()
exec(src.split("TFMAP =")[0])   # detect_sweeps, recent, roster_entries, run, I, DATA, MAKER, TAKER, SLIP, WARM

FUND = "D:/OSCAR/Documents/Trading Proyects/Oscilion/data/funding/binanceusdm/{c}_USDT_USDT.parquet"


def load_fund(coin):
    f = pd.read_parquet(FUND.format(c=coin)).sort_values("ts")
    return f["ts"].values.astype(float), f["funding_rate"].values.astype(float)


def run_f(df, side, exit_mode, safety_atr, entry, flips, tf, ft, fr):
    """Igual a run() de poc_sweep_filter pero con FUNDING real acumulado por trade."""
    op, hi, lo = df["open"].values, df["high"].values, df["low"].values
    atr = I.atr14(df).values; idx = df.index; n = len(df)
    up, dn = flips
    flip_arr = (dn if side > 0 else up)
    to_bars = int(48 * 3600 / (900 if tf == "15m" else 3600))
    amult = 2.0 if exit_mode == "atrstop" else safety_atr
    ivms = idx.view("int64") / 1e6
    trades = []; i = WARM
    while i < n - 1:
        if not entry[i]:
            i += 1; continue
        e_i = i + 1; epx = op[e_i]
        stop = epx - side * amult * atr[i] if amult else None
        exit_px = cost_out = None; t_out = None
        j = e_i
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
        fund = fr[a:b].sum()
        net = side * (exit_px / epx - 1) - MAKER - cost_out - side * fund
        trades.append((idx[e_i], net)); i = j + 1
    return pd.DataFrame(trades, columns=["t_in", "ret"]) if trades else None


def met(tr):
    if tr is None or len(tr) == 0:
        return dict(n=0, wr=0, exp=0, pf=0, ypos=0, ytot=0)
    r = tr["ret"]; by = tr.assign(y=tr["t_in"].dt.year).groupby("y")["ret"].mean()
    return dict(n=len(tr), wr=(r > 0).mean()*100, exp=r.mean()*1e4,
                pf=r[r > 0].sum()/max(abs(r[r <= 0].sum()), 1e-9),
                ypos=int((by > 0).sum()), ytot=int(len(by)))


def split_met(tr, cut="2025-01-01"):
    if tr is None:
        return met(None), met(None)
    cut = pd.Timestamp(cut)
    return met(tr[tr["t_in"] < cut]), met(tr[tr["t_in"] >= cut])


# combos: coin, tf, side, exit, safety, base-entry-fn key + filtros
def build(coin, tf, ema_len=200, W_=5, MAXAGE_=200, volwin=500):
    df = pd.read_parquet(DATA.format(c=coin, tf=tf))
    df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
    ents, flips = roster_entries(coin, df)
    # detector de barridos con W/MAXAGE perturbables
    global W, MAXAGE
    W, MAXAGE = W_, MAXAGE_
    sL, sS = detect_sweeps(df)
    c = df["close"]; green, red, regup, regdn = I.bx_parts(c)
    ema = c.ewm(span=ema_len, adjust=False).mean().values
    atr = I.atr14(df).values; atrpct = atr / c.values
    volmed = pd.Series(atrpct).rolling(volwin, min_periods=100).median().values
    return df, ents, flips, sL, sS, regup, regdn, ema, atrpct, volmed


def mask_for(combo, df, side, sL, sS, regup, regdn, ema, atrpct, volmed):
    c = df["close"].values
    m = np.ones(len(df), bool)
    for f in combo:
        if f.startswith("sweep"):
            F = int(f[5:]); m &= recent(sL if side > 0 else sS, F)
        elif f == "regime":
            m &= (regup if side > 0 else regdn)
        elif f == "trend":
            m &= (c > ema) if side > 0 else (c < ema)
        elif f == "vol":
            m &= atrpct >= volmed
    return m


COMBOS = {
    "S1-TRX-L": dict(coin="TRX", tf="1h", sid="S1-TRX-L", combo=["sweep6", "regime", "trend"]),
    "S6-XRP-L": dict(coin="XRP", tf="1h", sid="S6-XRP-L", combo=["trend"]),
    "S8-ETH-S": dict(coin="ETH", tf="1h", sid="S8-ETH-S", combo=["trend", "vol"]),
    "S4-SUI-S": dict(coin="SUI", tf="1h", sid="S4-SUI-S", combo=["sweep24"]),
}


def run_combo(spec, ema_len=200, W_=5, MAXAGE_=200, volwin=500):
    df, ents, flips, sL, sS, regup, regdn, ema, atrpct, volmed = build(
        spec["coin"], spec["tf"], ema_len, W_, MAXAGE_, volwin)
    ft, fr = load_fund(spec["coin"])
    side, em, sa, entry = ents[spec["sid"]]
    base = run_f(df, side, em, sa, entry, flips, spec["tf"], ft, fr)
    mask = mask_for(spec["combo"], df, side, sL, sS, regup, regdn, ema, atrpct, volmed)
    filt = run_f(df, side, em, sa, entry & mask, flips, spec["tf"], ft, fr)
    return base, filt, (df, ents, flips, sL, sS, regup, regdn, ema, atrpct, volmed, ft, side, em, sa, entry)


def main():
    for name, spec in COMBOS.items():
        base, filt, ctx = run_combo(spec)
        bf, ff = met(base), met(filt)
        bt_tr, bt_te = split_met(base); ft_tr, ft_te = split_met(filt)
        print(f"\n{'='*92}\n{name}  filtros={'+'.join(spec['combo'])}   (con FUNDING real)")
        print(f"  {'':18}{'n':>5}{'WR%':>6}{'exp_bps':>9}{'PF':>6}{'años+':>7}")
        print(f"  {'BASELINE full':18}{bf['n']:5}{bf['wr']:6.0f}{bf['exp']:9.1f}{bf['pf']:6.2f}{bf['ypos']:4}/{bf['ytot']}")
        print(f"  {'FILTRADO full':18}{ff['n']:5}{ff['wr']:6.0f}{ff['exp']:9.1f}{ff['pf']:6.2f}{ff['ypos']:4}/{ff['ytot']}")
        print(f"  -- OOS: TRAIN 23-24 / TEST 25-26 --")
        print(f"  {'base train':18}{bt_tr['n']:5}{bt_tr['wr']:6.0f}{bt_tr['exp']:9.1f}{bt_tr['pf']:6.2f}")
        print(f"  {'base test':18}{bt_te['n']:5}{bt_te['wr']:6.0f}{bt_te['exp']:9.1f}{bt_te['pf']:6.2f}")
        print(f"  {'filt train':18}{ft_tr['n']:5}{ft_tr['wr']:6.0f}{ft_tr['exp']:9.1f}{ft_tr['pf']:6.2f}")
        print(f"  {'filt test':18}{ft_te['n']:5}{ft_te['wr']:6.0f}{ft_te['exp']:9.1f}{ft_te['pf']:6.2f}")
        veredicto = "ROBUSTO OOS" if (ft_te['exp'] > 0 and ft_te['exp'] >= bt_te['exp'] and ft_te['n'] >= 10) else \
                    "DUDOSO (no mejora en test)" if ft_te['exp'] > 0 else "FALLA OOS (test negativo)"
        print(f"  >> OOS: {veredicto}")
        # sensibilidad
        print(f"  -- SENSIBILIDAD (exp_bps al perturbar knobs) --")
        perturb = []
        if any(f.startswith("sweep") for f in spec["combo"]):
            F0 = int([f for f in spec["combo"] if f.startswith("sweep")][0][5:])
            for F in (max(3, F0-3), F0, F0+3, F0+6):
                cb = [f"sweep{F}" if f.startswith("sweep") else f for f in spec["combo"]]
                _, fl, _ = run_combo({**spec, "combo": cb}); perturb.append((f"sweepF={F}", met(fl)["exp"]))
        if "trend" in spec["combo"]:
            for el in (150, 200, 250):
                _, fl, _ = run_combo(spec, ema_len=el); perturb.append((f"ema={el}", met(fl)["exp"]))
        if any(f.startswith("sweep") for f in spec["combo"]):
            for mg in (150, 200, 250):
                _, fl, _ = run_combo(spec, MAXAGE_=mg); perturb.append((f"maxage={mg}", met(fl)["exp"]))
        ex = [e for _, e in perturb]
        print("    " + "  ".join(f"{k}:{e:.0f}" for k, e in perturb))
        print(f"    rango exp: [{min(ex):.0f}, {max(ex):.0f}]  -> "
              f"{'ROBUSTO (todo positivo)' if min(ex) > 0 else 'FRAGIL (algun knob negativo)'}")


if __name__ == "__main__":
    main()
