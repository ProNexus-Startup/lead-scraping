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
