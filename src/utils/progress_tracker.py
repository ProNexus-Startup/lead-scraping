import json
import os
from datetime import datetime, timezone
from typing import Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ProgressTracker:
    """
    Tracks ZIP-level progress for a state scraping run.
    Saves state to a JSON file after every update so Ctrl+C never loses progress.
    """

    def __init__(self, progress_path: str):
        self.path = progress_path
        self._data: dict = {}

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def init_fresh(
        self,
        query: str,
        label: str,
        csv_path: str,
        zip_codes: List[str],
    ) -> None:
        self._data = {
            "query": query,
            "label": label,
            "csv_path": csv_path,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "zips": {z: "pending" for z in zip_codes},
            "totals": {
                "leads": 0,
                "success": 0,
                "no_website": 0,
                "crawl_failed": 0,
                "llm_failed": 0,
            },
        }
        self._save()
        logger.info(f"Progress file created: {self.path}")

    def load_existing(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            self._data = json.load(f)
        logger.info(f"Resumed from progress file: {self.path}")

    # ------------------------------------------------------------------
    # ZIP status updates
    # ------------------------------------------------------------------

    def mark_done(self, zip_code: str, leads: list) -> None:
        self._data["zips"][zip_code] = "done"
        t = self._data["totals"]
        t["leads"] += len(leads)
        for lead in leads:
            t[lead.status] = t.get(lead.status, 0) + 1
        self._save()

    def mark_failed(self, zip_code: str) -> None:
        self._data["zips"][zip_code] = "failed"
        self._save()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def csv_path(self) -> str:
        return self._data["csv_path"]

    @property
    def query(self) -> str:
        return self._data["query"]

    def pending_zips(self) -> List[str]:
        return [z for z, s in self._data["zips"].items() if s == "pending"]

    def zip_stats(self) -> Dict[str, int]:
        zips = self._data["zips"]
        return {
            "total":   len(zips),
            "done":    sum(1 for s in zips.values() if s == "done"),
            "failed":  sum(1 for s in zips.values() if s == "failed"),
            "pending": sum(1 for s in zips.values() if s == "pending"),
        }

    def totals(self) -> dict:
        return dict(self._data["totals"])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
