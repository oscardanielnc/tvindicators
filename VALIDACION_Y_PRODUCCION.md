# Validación (2ª revisión) y Ruta a Producción — tvindicators
**Fecha:** 2026-06-15 · auditoría `audit_robustez.py`

## 1) ¿Es real el Sharpe 4.07? — Segunda revisión honesta

**Lo que está BIEN (mecánica de los tests):** sin look-ahead (entrada open[i+1], señales en vela cerrada,
pivotes confirmados con lag), costos reales (maker/taker/slippage) + funding real, split IS/OOS,
sensibilidad a parámetros, dedup por correlación. La mecánica es sólida.

**Lo que NO es artefacto (verificado):**
- **Régimen:** Sharpe excluyendo 2024 (el año fuerte) = 3.76 (93% del full). Consistente por año
  (2022:3.19 / 2023:2.67 / 2024:4.93 / 2025:3.99 / 2026:6.26). NO depende de un solo régimen.
- **Correlación en estrés:** corr media entre estrategias = 0.027 en días normales y **−0.00 en los peores
  10% días**. La diversificación NO se evapora en días malos (el libro long/short está hedge-ado).
- Cola suave: peor mes −1.0%, maxDD −2.2%, peor trimestre +0.2%.

**El problema REAL (la advertencia de Kepler, bien diagnosticada):**
- **Solo 16/56 estrategias son significativas individualmente (t>2); 0 sobreviven corrección multi-test
  (t>3); mediana t-stat 1.65.** Es decir: **40 de 56 NO tienen edge estadísticamente distinguible del ruido
  todavía** (pocos trades, ~40-150 c/u en 3-4 años).
- El Sharpe alto viene del efecto √N (combinar muchas series poco correlacionadas). Eso reduce varianza
  AUNQUE algunas series tengan edge ≈0 → el Sharpe de cartera se ve genial aun si parte de las apuestas
  no tienen edge real. En vivo, las de edge≈0 regresan a ~0−costos y arrastran el Sharpe hacia abajo.

**Caveats que sesgan optimista (a tener presentes):** survivorship del universo (solo monedas que
sobrevivieron), fills maker asumidos, slippage fijo 0.02% (peor en alts finas), y el OOS se usó como gate
(así que el OOS ya no es 100% limpio). 

**Conclusión:** el backtest es un buen FILTRO, no una expectativa. **No confiar en 4.07 como Sharpe vivo.**
Expectativa realista: bastante por debajo (quizá 1.0-2.0 vivo). **El paper trading en vivo es el juez
insesgado** — y por eso es la fase actual. Las 40 con t<2 se confirman o se caen SOLO con datos vivos.

## 2) Captura de datos por trade (para decidir quedarse/irse)

Hoy se guarda: fechas, precios, lado, notional, leverage, stop, razón de salida, PnL, fees, funding,
ret%, velas, ATR de entrada. **Para el proyecto unificado conviene enriquecer cada trade con:**
- **MAE / MFE** (máxima excursión adversa/favorable) → ¿el SL está bien puesto?, ¿se cortan ganadores?
- **Contexto de entrada:** régimen de vol (ATR%), tendencia de BTC/mercado, funding al entrar, sesión/hora,
  qué filtros se activaron, valor del indicador en la señal.
- **Slippage realizado vs esperado** (calidad de ejecución).
- **Estrategias abiertas en paralelo** (para correlación viva real).
- **Comparación vs backtest** (BACKTEST_REF ya está) → ratio live/bt por trade y acumulado.

## 3) Ruta a producción

**Tensión de diseño:** el proyecto premia "pocas y buenas" (baja frecuencia) → validar cada estrategia
individualmente es LENTO. Números (gate = 25 trades vivos, asumiendo frecuencia ≈ backtest):
- ≤1.5 meses: **3**/56 · ≤3 meses: **3** · ≤6 meses: **14** · ≤12 meses: **37** · >12 meses: 19.
- Solo S2, S3, S7 (TRX/AVAX, alta frecuencia, t>2) llegan a 25 trades en ~6 semanas.

**Por eso la validación debe ser a nivel PORTAFOLIO/CLÚSTER, no solo por estrategia:**
el libro completo hace ~222 trades/mes → potencia estadística en ~2-3 meses, aunque cada estrategia sola
tarde años. 

**Ruta recomendada (lotes rodantes):**
1. **Sombra (ahora):** las 56 en paper acumulando trades vivos. Ya corriendo.
2. **Confirmación de cartera (~2-3 meses):** cuando el track VIVO AGREGADO confirme el backtest (mismo signo
   de expectancy, DD ≤1.5× esperado), salir a producción con **capital chico (1×)** sobre el libro.
3. **Lote 1 con capital real:** las que ya pasaron su gate vivo individual (alta frecuencia primero:
   S2/S3/S7 en ~6 sem) + el resto entra al libro con peso token hasta probarse.
4. **Graduación/retiro rodante:** subir peso a las que el vivo confirma; retirar las que el vivo condena
   (gate de `/api/evaluation`). Las de baja frecuencia se juzgan por contribución al clúster, no aisladas.
5. **Escalar apalancamiento** (1× → 2×) solo tras meses de vivo consistente.

**Estimación:** primer lote chico a producción en **~2-3 meses** (confirmación de cartera + las 3-14 más
rápidas). Roster maduro (incl. las de 1 trade/mes) **6-18 meses**. Las muy lentas quizá nunca alcancen
significancia individual → se quedan/van por su aporte al portafolio, no por su t-stat solo.

## Próximos pasos sugeridos
- Enriquecer la captura de datos por trade (MAE/MFE + contexto) — alto valor para el unificado.
- Tracker de confirmación a nivel cartera (live agregado vs backtest) además del gate por estrategia.
- Mantener el universo descargando data y vigilar survivorship al añadir monedas.
