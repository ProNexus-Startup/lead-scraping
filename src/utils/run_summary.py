import json
from typing import List

from src.models.lead import Lead
from src.utils.logger import get_logger

logger = get_logger(__name__)

_WIDTH = 54

# ANSI color codes — console only, never written to log files
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_RESET  = "\033[0m"


def write_run_summary(
    leads: List[Lead],
    csv_path: str,
    query: str,
    provider: str,
    model: str,
    duration_seconds: float,
) -> str:
    """
    Prints a quality summary to the console and writes a JSON file alongside the CSV.
    Returns the path to the written summary file.
    """
    metrics = _compute_metrics(leads, query, provider, model, duration_seconds)
    _print_summary(metrics)
    return _write_json(metrics, csv_path)


def _compute_metrics(
    leads: List[Lead],
    query: str,
    provider: str,
    model: str,
    duration_seconds: float,
) -> dict:
    total = len(leads)

    status_counts = {"success": 0, "no_website": 0, "crawl_failed": 0, "llm_failed": 0}
    for lead in leads:
        status_counts[lead.status] = status_counts.get(lead.status, 0) + 1

    email_count = sum(1 for l in leads if l.owner_email_primary)
    name_count = sum(1 for l in leads if l.owner_name)

    confidence_counts = {"high": 0, "medium": 0, "low": 0}
    successful = [l for l in leads if l.status == "success"]
    for lead in successful:
        key = (lead.llm_confidence or "low").lower()
        confidence_counts[key] = confidence_counts.get(key, 0) + 1

    def pct(n: int, d: int) -> float:
        return round(n / d * 100, 1) if d else 0.0

    return {
        "run": {
            "query": query,
            "provider": provider,
            "model": model,
            "duration_seconds": round(duration_seconds, 1),
        },
        "volume": {
            "total": total,
            "success": status_counts["success"],
            "success_rate_pct": pct(status_counts["success"], total),
            "email_fill_rate_pct": pct(email_count, total),
            "owner_name_fill_rate_pct": pct(name_count, total),
            "email_count": email_count,
            "name_count": name_count,
        },
        "confidence": {
            "high": confidence_counts.get("high", 0),
            "medium": confidence_counts.get("medium", 0),
            "low": confidence_counts.get("low", 0),
            "high_pct": pct(confidence_counts.get("high", 0), len(successful)),
            "medium_pct": pct(confidence_counts.get("medium", 0), len(successful)),
            "low_pct": pct(confidence_counts.get("low", 0), len(successful)),
        },
        "pipeline_status": {
            "no_website": status_counts.get("no_website", 0),
            "crawl_failed": status_counts.get("crawl_failed", 0),
            "llm_failed": status_counts.get("llm_failed", 0),
            "no_website_pct": pct(status_counts.get("no_website", 0), total),
            "crawl_failed_pct": pct(status_counts.get("crawl_failed", 0), total),
            "llm_failed_pct": pct(status_counts.get("llm_failed", 0), total),
        },
    }


def _print_summary(m: dict) -> None:
    run = m["run"]
    vol = m["volume"]
    conf = m["confidence"]
    ps = m["pipeline_status"]

    sep = "=" * _WIDTH
    thin = "-" * _WIDTH

    def row(label: str, value: str) -> str:
        return f"  {label:<22}{value}"

    def stat(label: str, count: int, total: int, pct: float, color: str = _RESET) -> str:
        return f"  {label:<22}{color}{count:>4} / {total:<4}  {pct:>5.1f}%{_RESET}"

    def count_row(label: str, count: int, pct: float, color: str = _RESET) -> str:
        return f"  {label:<22}{color}{count:>4}          {pct:>5.1f}%{_RESET}"

    lines = [
        "",
        sep,
        "  PIPELINE RUN SUMMARY",
        thin,
        row("Query",    run["query"]),
        row("Provider", f"{run['provider']}  |  {run['model']}"),
        row("Duration", f"{run['duration_seconds']}s  |  {vol['total']} leads processed"),
        thin,
        "  EXTRACTION QUALITY",
        stat("Success rate",     vol["success"],     vol["total"], vol["success_rate_pct"],       _GREEN),
        stat("Email fill rate",  vol["email_count"], vol["total"], vol["email_fill_rate_pct"],    _CYAN),
        stat("Owner name rate",  vol["name_count"],  vol["total"], vol["owner_name_fill_rate_pct"], _CYAN),
        thin,
        f"  CONFIDENCE  (successful leads: {vol['success']})",
        count_row("High",   conf["high"],   conf["high_pct"],   _GREEN),
        count_row("Medium", conf["medium"], conf["medium_pct"], _YELLOW),
        count_row("Low",    conf["low"],    conf["low_pct"],    _RED),
        thin,
        "  PIPELINE STATUS",
        count_row("No website",   ps["no_website"],   ps["no_website_pct"],   _YELLOW),
        count_row("Crawl failed", ps["crawl_failed"], ps["crawl_failed_pct"], _RED),
        count_row("LLM failed",   ps["llm_failed"],   ps["llm_failed_pct"],   _RED),
        sep,
        "",
    ]

    print("\n".join(lines))


def _write_json(metrics: dict, csv_path: str) -> str:
    summary_path = csv_path.replace(".csv", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Summary written to {summary_path}")
    return summary_path
