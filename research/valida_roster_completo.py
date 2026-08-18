"""Cierre de validacion: correlacion de las 8 nuevas vs el ROSTER COMPLETO (S1-S21).

valida_profunda midio corr vs un proxy (S1-S9). Aqui reconstruyo las 21 entradas REALES
en forma de array (identicas a tvbot/strategies.py: mismos indicadores, mismos filtros) y
respondo la pregunta de riesgo que queda:
  - El roster ya tiene 11 SHORTS de alts. Las 5 nuevas VTX-S son shorts de alts tambien.
    ¿Se concentra el libro de shorts? -> nº efectivo de apuestas entre los 16 shorts.
  - corr de cada nueva vs el roster completo (no solo S1-S9).
  - Portafolio 21 vs 21+8 (vol-parity): ¿mejora Sharpe/DD o solo apila beta short de alts?

Uso: python valida_roster_completo.py
"""
from pathlib import Path as _P
import sys as _sys
_ROOT = _P(__file__).resolve().parents[1]
_sys.path.insert(0, str(_ROOT))
import numpy as np
import pandas as pd

src = open(str(_ROOT / "research/valida_profunda_nuevos.py"), encoding="utf-8").read()
exec(src.split("\ndef main():")[0])   # TOP8, daily_pnl, build_tr, run_f, met, filt_arrays, load_fund, DATA, I, basket_stats...

# --- reconstruccion array-form de las 21 entradas (fiel a strategies.py) ---
COIN_TF = {  # sid -> (coin, tf, side, exit_mode, safety_atr)
    "S1": ("TRX", "1h", +1, "atrstop", None), "S2": ("TRX", "1h", +1, "flip", 3.0),
    "S3": ("TRX", "15m", +1, "flip", None), "S4": ("SUI", "1h", -1, "atrstop", None),
    "S5": ("LTC", "1h", -1, "atrstop", None), "S6": ("XRP", "1h", +1, "flip", None),
    "S7": ("AVAX", "15m", +1, "flip", None), "S8": ("ETH", "1h", -1, "atrstop", None),
    "S9": ("BTC", "1h", +1, "atrstop", None), "S10": ("DOT", "1h", -1, "atrstop", None),
    "S11": ("ADA", "1h", -1, "atrstop", None), "S12": ("ADA", "1h", -1, "atrstop", None),
    "S13": ("DOT", "1h", -1, "atrstop", None), "S14": ("XLM", "1h", +1, "flip", 3.0),
    "S15": ("RUNE", "1h", +1, "flip", None), "S16": ("IMX", "1h", +1, "flip", None),
    "S17": ("FLOW", "1h", +1, "flip", None), "S18": ("EGLD", "1h", -1, "atrstop", None),
    "S19": ("FET", "1h", -1, "atrstop", None), "S20": ("APT", "1h", -1, "atrstop", None),
    "S21": ("GRT", "1h", -1, "atrstop", None),
}


def coin_arrays(coin, df):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    gl, rs, regup, regdn = I.bx_parts(c)
    up, dn, sd = I.st_flips(df)
    don = I.dch_trend(c, h, l, 20)
    hc = I.hacolt(o, h, l, c)
    slr, _ = I.ribbon_strength(c, h, l)
    tm = np.asarray(I.tm_align_edge(c))
    trL = np.asarray(I.ema_trend_ok(c, +1)); trS = np.asarray(I.ema_trend_ok(c, -1))
    vol = np.asarray(I.vol_ok(df))
    sL, sS = I.liquidity_sweeps(df)
    swL6 = np.asarray(I.sweep_recent(sL, 6)); swS6 = np.asarray(I.sweep_recent(sS, 6))
    swS12 = np.asarray(I.sweep_recent(sS, 12))
    gl, rs, regup, regdn = map(np.asarray, (gl, rs, regup, regdn))
    full = slr == 10; full_ev = full & ~np.roll(full, 1)
    tm_red = tm_red_exit(df)
    A = dict(gl=gl, rs=rs, regup=regup, regdn=regdn, up=up, dn=dn, sd=sd, don=don,
             hc=hc, slr=slr, tm=tm, trL=trL, trS=trS, vol=vol, swL6=swL6, swS6=swS6,
             swS12=swS12, full_ev=full_ev, tm_red=tm_red)
    return A


def tm_red_exit(df):
    c = df["close"]
    fmacd = I.pine_ema(c, 8) - I.pine_ema(c, 21)
    fhist = (fmacd - I.pine_ema(fmacd, 5)) > 0
    neg = ((~fhist) & (I.pine_rsi(c, 13) < 50) & (I.pine_rsi(c, 5) < 50)).values
    return neg & ~np.roll(neg, 1)


def entry_array(sid, A):
    g = A
    return {
        "S1": g["gl"] & g["swL6"] & g["regup"] & g["trL"],
        "S2": g["tm"],
        "S3": g["up"] & (g["hc"] == 1) & (g["slr"] >= 8),
        "S4": g["rs"] & g["regdn"],
        "S5": g["dn"] & (g["don"] == -1),
        "S6": g["up"] & (g["hc"] == 1) & g["trL"],
        "S7": g["up"] & (g["don"] == 1) & (g["hc"] == 1),
        "S8": g["rs"] & (g["don"] == -1) & g["trS"] & g["vol"],
        "S9": g["full_ev"] & g["regup"] & (g["sd"] == 1),
        "S10": g["rs"] & (g["don"] == -1) & g["swS6"],
        "S11": g["rs"] & g["regdn"] & g["trS"] & g["vol"],
        "S12": g["rs"] & (g["don"] == -1) & g["swS6"],
        "S13": g["dn"] & (g["don"] == -1) & g["trS"],
        "S14": g["tm"] & g["regup"] & g["trL"] & g["vol"],
        "S15": g["up"] & (g["don"] == 1) & (g["hc"] == 1) & g["regup"] & g["trL"],
        "S16": g["up"] & (g["don"] == 1) & (g["hc"] == 1) & g["trL"] & g["vol"],
        "S17": g["up"] & (g["hc"] == 1) & g["trL"] & g["vol"],
        "S18": g["rs"] & g["regdn"] & g["swS6"],
        "S19": g["rs"] & (g["don"] == -1) & g["swS12"],
        "S20": g["dn"] & (g["don"] == -1) & g["regdn"] & g["trS"],
        "S21": g["rs"] & g["regdn"] & g["swS6"] & g["trS"],
    }[sid]


def roster_daily_all():
    """{sid: serie diaria de PnL} para las 21, via run_f real (mismo motor/funding)."""
    out = {}
    by_coin = {}
    for sid, (coin, tf, side, em, sa) in COIN_TF.items():
        by_coin.setdefault((coin, tf), []).append((sid, side, em, sa))
    for (coin, tf), lst in by_coin.items():
        df = pd.read_parquet(DATA.format(c=coin, tf=tf))
        df["dt"] = pd.to_datetime(df["ts"], unit="ms"); df = df.set_index("dt").sort_index()
        ft, fr = load_fund(coin)
        A = coin_arrays(coin, df)
        up, dn = A["up"], A["dn"]
        for sid, side, em, sa in lst:
            ent = np.asarray(entry_array(sid, A))
            flips = (up, A["tm_red"]) if sid in ("S2", "S14") else (up, dn)
            tr = run_f(df, side, em, sa, ent, flips, tf, ft, fr)
            if tr is not None:
                out[sid] = tr.set_index("t_in")["ret"].resample("1D").sum()
    return out


def eff_bets(M):
    cc = M.corr().values
    ev = np.linalg.eigvalsh(cc)
    return (ev.sum() ** 2) / (ev ** 2).sum()


def main():
    rost = roster_daily_all()
    for k in rost:
        rost[k].name = k
    print(f"Roster reconstruido: {len(rost)}/21 estrategias con trades.")

    # nuevas
    new_series = {}
    for (c, s, sd, fs) in TOP8:
        nm = f"{c}-{s}-{'L' if sd>0 else 'S'}"
        d = daily_pnl(c, s, sd, fs); d.name = nm; new_series[nm] = d

    # --- 1) concentracion del LIBRO DE SHORTS (existentes + nuevos) ---
    existing_shorts = [k for k, (co, tf, sd, em, sa) in COIN_TF.items() if sd < 0]
    new_shorts = [nm for nm in new_series if nm.endswith("-S")]
    short_M = pd.concat([rost[s] for s in existing_shorts if s in rost] +
                        [new_series[n] for n in new_shorts], axis=1).fillna(0)
    eb_before = eff_bets(pd.concat([rost[s] for s in existing_shorts if s in rost], axis=1).fillna(0))
    eb_after = eff_bets(short_M)
    print(f"\n{'='*88}\n1) LIBRO DE SHORTS")
    print(f"  shorts existentes: {len(existing_shorts)}  -> nº efectivo apuestas: {eb_before:.1f}")
    print(f"  + {len(new_shorts)} nuevas VTX-S ({', '.join(new_shorts)})")
    print(f"  shorts totales: {short_M.shape[1]}  -> nº efectivo apuestas: {eb_after:.1f}")
    print(f"  delta apuestas reales: {eb_after - eb_before:+.1f}  -> "
          f"{'AGREGAN diversificacion real' if (eb_after-eb_before) > len(new_shorts)*0.5 else 'concentran (poca apuesta nueva)'}")

    # --- 2) corr de cada nueva vs roster COMPLETO (agregado) ---
    Rall = pd.concat(list(rost.values()), axis=1).fillna(0).sum(axis=1)
    print(f"\n{'='*88}\n2) CORR de cada nueva vs ROSTER COMPLETO (S1-S21 agregado)")
    for nm, d in new_series.items():
        al = pd.concat([d.rename("x"), Rall.rename("R")], axis=1).fillna(0)
        print(f"  {nm:14} corr {al['x'].corr(al['R']):+.2f}")

    # --- 3) portafolio 21 vs 21+8 (vol-parity 1x) ---
    def vp_basket(series_list):
        M = pd.concat(series_list, axis=1).fillna(0)
        sig = M.std().replace(0, np.nan); w = (1/sig); w = (w/w.sum()).values
        port = (M * w).sum(axis=1); eq = (1+port).cumprod()
        yrs = (M.index[-1]-M.index[0]).days/365.25
        return dict(cagr=eq.iloc[-1]**(1/yrs)-1, dd=(eq/eq.cummax()-1).min(),
                    sharpe=port.mean()/port.std()*np.sqrt(365) if port.std()>0 else 0)
    p21 = vp_basket(list(rost.values()))
    p29 = vp_basket(list(rost.values()) + list(new_series.values()))
    print(f"\n{'='*88}\n3) PORTAFOLIO vol-parity 1x  (roster solo  vs  roster+8 nuevas)")
    print(f"  {'':10}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}")
    print(f"  {'21 solo':10}{p21['cagr']*100:7.0f}%{p21['dd']*100:7.0f}%{p21['sharpe']:8.2f}")
    print(f"  {'21 + 8':10}{p29['cagr']*100:7.0f}%{p29['dd']*100:7.0f}%{p29['sharpe']:8.2f}")
    print(f"  delta:    CAGR {(p29['cagr']-p21['cagr'])*100:+.0f}pp  "
          f"DD {(p29['dd']-p21['dd'])*100:+.0f}pp  Sharpe {p29['sharpe']-p21['sharpe']:+.2f}")


if __name__ == "__main__":
    main()
