import csv
import os
from datetime import datetime
from typing import List

from src.models.lead import Lead
from src.utils.logger import get_logger

logger = get_logger(__name__)


def write_leads_csv(leads: List[Lead], output_dir: str, label: str = "") -> str:
    os.makedirs(output_dir, exist_ok=True)
    slug = f"_{label.replace(' ', '_')}" if label else ""
    filename = f"leads_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}{slug}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Lead.csv_fieldnames())
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_csv_row())

    logger.info(f"Wrote {len(leads)} leads to {filepath}")
    return filepath


def init_csv(csv_path: str) -> None:
    """Create a CSV file with headers only. Used at the start of a ZIP run."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Lead.csv_fieldnames())
        writer.writeheader()


def append_leads_csv(leads: List[Lead], csv_path: str) -> None:
    """Append leads to an existing CSV. Call after each ZIP is processed."""
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=Lead.csv_fieldnames())
        for lead in leads:
            writer.writerow(lead.to_csv_row())
