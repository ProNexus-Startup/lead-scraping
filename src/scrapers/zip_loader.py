import csv
import os
from typing import List

from src.utils.logger import get_logger

logger = get_logger(__name__)

_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "us-zip-codes.csv",
)


def load_zips_for_state(state: str, min_population: int = 1000) -> List[str]:
    """Return all ZIP codes for a US state with population >= min_population."""
    state = state.upper().strip()
    zips = []

    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("state", "").upper() != state:
                continue
            try:
                pop = int(row.get("irs_estimated_population") or 0)
            except ValueError:
                pop = 0
            if pop >= min_population:
                zips.append(str(row["zip"]).zfill(5))

    logger.info(f"Loaded {len(zips)} ZIP codes for state={state} min_pop={min_population}")
    return zips


def parse_zip_list(zips_str: str) -> List[str]:
    """Parse a comma-separated string of ZIP codes into a clean list."""
    return [z.strip().zfill(5) for z in zips_str.split(",") if z.strip()]
