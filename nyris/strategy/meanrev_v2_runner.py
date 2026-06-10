"""Runner MEAN-REVERSION v2 (oneshot, paper) — univers ELARGI top-100 paires USDT liquides.

Meme moteur/logique que meanrev_runner (RSI14<35 long, exit close>SMA10 ou 20j) mais sur ~100
actifs au lieu de 13. run_id=live-meanrev-v2, lock dedie. ISOLE : le v1 (13 alts) reste intact
comme temoin ; baseline gele. Valide en backtest (PF 1.58 sur 30j, generalise).

Exécution : python -m nyris.strategy.meanrev_v2_runner
"""

from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager

from nyris.core.database import SessionLocal
from nyris.core.logging import configure_logging
from nyris.strategy.meanrev_models import MeanRevParams
from nyris.strategy.meanrev_runner import run_cycle
from nyris.strategy.meanrev_v2_universe import PAIRS

logger = logging.getLogger("nyris.meanrev_v2_runner")
LOCK_PATH = "/srv/nyris/meanrev-v2-runner.lock"
MR_V2 = MeanRevParams(universe=PAIRS, run_id="live-meanrev-v2")


class MeanRevV2Busy(Exception):
    pass


@contextmanager
def cycle_lock(path: str = LOCK_PATH):
    fh = open(path, "w")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        fh.close()
        raise MeanRevV2Busy() from exc
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _main() -> None:
    configure_logging()
    try:
        with cycle_lock():
            with SessionLocal() as db:
                summary = run_cycle(db, MR_V2)
            logger.info("cycle meanrev-v2 terminé: %s", summary)
            print(json.dumps(summary, ensure_ascii=False))
    except MeanRevV2Busy:
        logger.warning("un autre cycle meanrev-v2 est en cours, abandon")
        print('{"status": "busy"}')


if __name__ == "__main__":
    _main()
