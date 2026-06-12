import logging
import logging.handlers
from datetime import datetime

import config


def _lima_time(*args):
    return datetime.now(config.LIMA_TZ).timetuple()


def setup():
    logging.Formatter.converter = _lima_time      # logs en hora de Lima
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    fh = logging.handlers.RotatingFileHandler(
        config.LOG_DIR / "tvbot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
