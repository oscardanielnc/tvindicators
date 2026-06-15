# Tests adicionales: selectividad · SL cercano · multi-TF

Entrada event+cooldown · exits ATR · costos 13.0bps RT · ret_pess (conservador) · IS<2026 / OOS 2026
_gross_bps = exp + costo (el edge BRUTO antes de comisiones; si ~0, la entrada no predice nada)._

| coin | TF | tr/día | mejor cfg | WR | exp_bps | gross_bps | PF | IS/OOS | peor1 | SL más cercano | veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 1m | 5.7 | TP3.0/SL1.0×ATR | 17% | -12.6 | +0.4 | 0.15 | -12/-13 | -111 | SLcerca exp=-13 peor=-48 | sin edge |
| BTC | 5m | 4.5 | TP3.0/SL1.0×ATR | 26% | -12.0 | +1.0 | 0.48 | -12/-14 | -164 | SLcerca exp=-13 peor=-91 | sin edge |
| BTC | 15m | 1.8 | TP3.0/SL3.0×ATR | 50% | -12.3 | +0.7 | 0.78 | -14/-1 | -511 | SLcerca exp=-14 peor=-107 | sin edge |
| BTC | 1h | 0.8 | TP1.5/SL3.0×ATR | 69% | -4.7 | +8.3 | 0.93 | -6/+6 | -996 | SLcerca exp=-13 peor=-177 | sin edge |
| ETH | 1m | 5.5 | TP3.0/SL2.0×ATR | 37% | -12.0 | +1.0 | 0.42 | -12/-13 | -146 | SLcerca exp=-13 peor=-49 | sin edge |
| ETH | 5m | 4.2 | TP3.0/SL1.5×ATR | 35% | -10.7 | +2.3 | 0.68 | -10/-12 | -229 | SLcerca exp=-13 peor=-91 | sin edge |
| ETH | 15m | 2.7 | TP1.5/SL2.0×ATR | 57% | -12.8 | +0.2 | 0.70 | -12/-17 | -595 | SLcerca exp=-14 peor=-159 | sin edge |
| ETH | 1h | 0.7 | TP2.0/SL3.0×ATR | 61% | -5.2 | +7.8 | 0.96 | -10/+34 | -1382 | SLcerca exp=-13 peor=-241 | sin edge |