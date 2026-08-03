"""Configuracion central del bot tvindicators (paper trading)."""
import os
from datetime import timedelta, timezone
from pathlib import Path

# Todo el sistema (DB, logs, API) trabaja en hora de Lima, Peru (UTC-5, sin DST)
LIMA_TZ = timezone(timedelta(hours=-5), name="America/Lima")

ROOT = Path(__file__).parent
DATA_DIR = Path(os.getenv("TVBOT_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.getenv("TVBOT_DB", DATA_DIR / "tvbot.db"))
LOG_DIR = Path(os.getenv("TVBOT_LOG_DIR", DATA_DIR / "logs"))

# --- Capital simulado ---
CAPITAL_INICIAL = float(os.getenv("TVBOT_CAPITAL", "1000"))
MARGIN_PCT = float(os.getenv("TVBOT_MARGIN_PCT", "0.10"))      # margen fijo por trade ($100 de $1000)
LEVERAGE = float(os.getenv("TVBOT_LEVERAGE", "5"))             # leverage de FALLBACK (si no hay stop)
MARGIN_MODE = os.getenv("TVBOT_MARGIN_MODE", "fixed")          # fixed = 10% del capital inicial

# --- Modo de sizing ---
# 'flat'  = FASE DE MEDICIÓN (actual): nocional constante, cada trade pesa igual en el PnL.
#           Es la única forma de que el dólar sea un estimador limpio del edge: con el sizing
#           por riesgo, cripto-short rindió +88 USD con 0.0 bps/trade — el beneficio venía del
#           leverage variable, no de la señal (auditoría 03/08/2026).
# 'risk'  = sizing por riesgo (abajo). Se reactiva cuando una tesis esté APROBADA como rentable
#           y toque calibrarle su leverage óptimo por varianza.
SIZING_MODE = os.getenv("TVBOT_SIZING_MODE", "flat")
FLAT_LEVERAGE = float(os.getenv("TVBOT_FLAT_LEVERAGE", "3"))   # ~el leverage medio del histórico

# --- Sizing por RIESGO (leverage dinámico por volatilidad) — inactivo en fase de medición ---
# Cada trade arriesga RISK_PER_TRADE del capital si toca el stop. El leverage se deriva de la
# distancia al stop (ATR de cada moneda): leverage = R*capital / (dist_stop * margen). Margen fijo.
# Ver METODOLOGIA_PRODUCCION.md §5/§5.1. R calibrado a maxDD anual <=25% al p95 (calibra_R.py).
RISK_PER_TRADE = float(os.getenv("TVBOT_RISK_PER_TRADE", "0.005"))  # 0.5% del capital por trade
MAX_LEVERAGE = float(os.getenv("TVBOT_MAX_LEVERAGE", "10"))         # tope de seguridad (liquidación)

# --- Costos (identicos al backtest validado) ---
MAKER_FEE = 0.0002
TAKER_FEE = 0.00045
SLIPPAGE = 0.0002          # se aplica en salidas por stop (market)

# --- Ejecucion ---
EXCHANGE = os.getenv("TVBOT_EXCHANGE", "binanceusdm")
WARMUP_BARS = 1000          # HACOLT/TEMA55 necesitan cola larga
CYCLE_OFFSET_S = 20         # corre 20s despues del cierre de vela
TIMEOUT_HOURS = 48
ATR_MULT = 2.0
CIRCUIT_BREAKER_ERRORS = 5  # errores consecutivos -> pausa
CIRCUIT_BREAKER_PAUSE_S = 900

# --- Gates de producción (graduación de paper -> capital real) ---
# Por estrategia: pasa a producción si cumple TODO esto en vivo.
GATE_MIN_TRADES = int(os.getenv("TVBOT_GATE_TRADES", "20"))     # nº trades cerrados vivos
GATE_MIN_RATIO = float(os.getenv("TVBOT_GATE_RATIO", "0.30"))   # exp_live / exp_backtest (conserva >=30% del edge)
GATE_MIN_PF = float(os.getenv("TVBOT_GATE_PF", "1.2"))          # profit factor vivo
# Por cartera: lote 1 a producción si el track AGREGADO confirma el backtest.
GATE_PORT_MIN_TRADES = int(os.getenv("TVBOT_GATE_PORT_TRADES", "150"))
GATE_PORT_MIN_CONFIRMED = int(os.getenv("TVBOT_GATE_PORT_CONFIRMED", "8"))  # nº estrategias confirmadas
# Por TESIS (unidad de decisión real en fase de medición, ver tvbot/theses.py): las estrategias
# de una misma apuesta se agrupan para juntar potencia estadística. Exige SIGNIFICANCIA, no solo
# PnL>0 — es más estricto que el gate por estrategia, no menos.
GATE_THESIS_MIN_TRADES = int(os.getenv("TVBOT_GATE_TH_TRADES", "80"))
GATE_THESIS_MIN_T = float(os.getenv("TVBOT_GATE_TH_T", "2.0"))    # t-stat de la expectancia en bps
GATE_THESIS_MIN_PF = float(os.getenv("TVBOT_GATE_TH_PF", "1.15"))

# --- API ---
API_HOST = os.getenv("TVBOT_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("TVBOT_API_PORT", "8090"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
