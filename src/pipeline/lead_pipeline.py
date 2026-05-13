import asyncio
import csv
import os
import time
from datetime import datetime, timezone
from typing import List, Set

import config.settings as settings
from src.extractors.llm_extractor import extract_owner
from src.models.lead import Lead
from src.scrapers.maps_scraper import search_businesses
from src.scrapers.web_crawler import crawl_domain, is_social_or_directory_url
from src.utils.csv_writer import append_leads_csv, init_csv, write_leads_csv
from src.utils.logger import get_logger
from src.utils.progress_tracker import ProgressTracker
from src.utils.run_summary import write_run_summary

logger = get_logger(__name__)


async def run(query: str, limit: int = 1, output_label: str = "") -> str:
    """
    Full pipeline: Maps → Crawl → LLM → CSV.
    Returns the path to the written CSV file.
    """
    logger.info(
        f"=== Pipeline start: query='{query}' limit={limit} "
        f"concurrency={settings.MAX_CONCURRENT_LEADS} provider={settings.LLM_PROVIDER} ==="
    )

    leads = search_businesses(query, limit=limit)
    if not leads:
        logger.warning("No businesses returned from Maps API. Check your API key and query.")
        return ""

    model = settings.CEREBRAS_MODEL if settings.LLM_PROVIDER == "cerebras" else settings.GROQ_MODEL
    start = time.perf_counter()

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_LEADS)
    await asyncio.gather(*[_process_lead(lead, semaphore) for lead in leads])

    duration = time.perf_counter() - start
    label = output_label or query
    csv_path = write_leads_csv(leads, settings.OUTPUT_DIR, label=label)
    write_run_summary(
        leads=leads,
        csv_path=csv_path,
        query=query,
        provider=settings.LLM_PROVIDER,
        model=model,
        duration_seconds=duration,
    )

    success_count = sum(1 for l in leads if l.status == "success")
    logger.info(
        f"=== Pipeline done: {len(leads)} total, {success_count} with owner extracted ==="
    )
    return csv_path


async def _process_lead(lead: Lead, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        if not lead.website:
            lead.status = "no_website"
            logger.info(f"  No website for {lead.business_name}")
            return

        if is_social_or_directory_url(lead.website):
            lead.status = "no_website"
            logger.info(f"  Social/directory URL listed as website for {lead.business_name}: {lead.website}")
            return

        logger.info(f"  Crawling {lead.website}")
        try:
            page_text = await crawl_domain(lead.website)
        except Exception as exc:
            logger.error(f"  Crawl error for {lead.website}: {exc}")
            lead.status = "crawl_failed"
            return

        if not page_text:
            lead.status = "crawl_failed"
            logger.warning(f"  No text extracted from {lead.website}")
            return

        logger.info(f"  Running LLM extraction for {lead.website}")
        result = await extract_owner(lead.website, page_text)

        lead.business_name_normalized       = result.get("business_name_normalized")
        lead.owner_first_name               = result.get("owner_first_name")
        lead.owner_last_name                = result.get("owner_last_name")
        lead.owner_name                     = result.get("owner_name")
        lead.owner_source_page              = result.get("owner_source_url")
        lead.owner_evidence_text            = result.get("owner_evidence_text")
        lead.email_owner_personal           = result.get("email_owner_personal")
        lead.email_owner_personal_source    = result.get("email_owner_personal_source")
        lead.email_owner_likely             = result.get("email_owner_likely")
        lead.email_owner_likely_source      = result.get("email_owner_likely_source")
        lead.email_generic                  = result.get("email_generic")
        lead.email_generic_source           = result.get("email_generic_source")
        lead.email_other                    = result.get("email_other")
        lead.recommended_email              = result.get("recommended_email")
        lead.recommended_email_type         = result.get("recommended_email_type")
        lead.owner_candidates               = result.get("owner_candidates")
        lead.llm_confidence                 = result.get("confidence")
        lead.llm_reasoning                  = result.get("reasoning")

        if lead.owner_name or lead.email_owner_personal or lead.email_owner_likely:
            lead.status = "success"
            logger.info(
                f"  Found: {lead.owner_name} <{lead.recommended_email}> "
                f"(confidence={lead.llm_confidence}) — {lead.llm_reasoning}"
            )
        else:
            lead.status = "llm_failed"
            logger.info(f"  LLM could not identify owner for {lead.website}. Reason: {lead.llm_reasoning}")


async def run_zips(
    query: str,
    zip_codes: List[str],
    limit_per_zip: int = 5,
    output_label: str = "",
    resume: bool = False,
) -> str:
    """
    ZIP-based pipeline with stop/resume support.
    Processes one ZIP at a time: Maps → deduplicate → Crawl → LLM → append CSV → save progress.
    Returns the path to the written CSV file.
    """
    from tqdm import tqdm

    os.makedirs(settings.PROGRESS_DIR, exist_ok=True)
    label = output_label or query.replace(" ", "_")
    progress_path = os.path.join(settings.PROGRESS_DIR, f"{label}.json")
    tracker = ProgressTracker(progress_path)
    seen: Set[str] = set()

    if resume and os.path.exists(progress_path):
        tracker.load_existing()
        csv_path = tracker.csv_path
        seen = _rebuild_seen_from_csv(csv_path)
        pending = tracker.pending_zips()
        zstats = tracker.zip_stats()
        print(f"Resuming: {zstats['done']} ZIPs done, {len(pending)} pending, {zstats['failed']} failed")
    else:
        slug = label.replace(" ", "_")
        filename = f"leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{slug}.csv"
        csv_path = os.path.join(settings.OUTPUT_DIR, filename)
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        tracker.init_fresh(query=query, label=label, csv_path=csv_path, zip_codes=zip_codes)
        init_csv(csv_path)
        pending = zip_codes

    if not pending:
        print("All ZIPs already completed. Nothing to do.")
        return tracker.csv_path

    logger.info(
        f"=== ZIP pipeline start: query='{query}' pending={len(pending)} "
        f"limit_per_zip={limit_per_zip} provider={settings.LLM_PROVIDER} ==="
    )

    start = time.perf_counter()
    zstats = tracker.zip_stats()

    try:
        with tqdm(
            total=zstats["total"],
            initial=zstats["done"] + zstats["failed"],
            desc=f"{query[:25]}",
            unit="ZIP",
            dynamic_ncols=True,
            colour="green",
        ) as pbar:
            totals = tracker.totals()
            pbar.set_postfix(leads=totals["leads"], failed=zstats["failed"])

            for zip_code in pending:
                zip_query = f"{query} in {zip_code}"

                try:
                    raw_leads = search_businesses(zip_query, limit=limit_per_zip)
                except Exception as exc:
                    logger.error(f"Maps API error for ZIP {zip_code}: {exc}")
                    tracker.mark_failed(zip_code)
                    pbar.update(1)
                    pbar.set_postfix(leads=tracker.totals()["leads"], failed=tracker.zip_stats()["failed"])
                    continue

                # Deduplicate against everything already seen
                new_leads = []
                for lead in raw_leads:
                    key = (
                        lead.website.lower()
                        if lead.website
                        else f"{lead.business_name}|{lead.address}".lower()
                    )
                    if key not in seen:
                        seen.add(key)
                        new_leads.append(lead)

                # Crawl + LLM for this ZIP's unique leads
                if new_leads:
                    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_LEADS)
                    await asyncio.gather(*[_process_lead(lead, semaphore) for lead in new_leads])
                    append_leads_csv(new_leads, csv_path)

                tracker.mark_done(zip_code, new_leads)
                pbar.update(1)
                pbar.set_postfix(leads=tracker.totals()["leads"], failed=tracker.zip_stats()["failed"])

    except KeyboardInterrupt:
        zstats = tracker.zip_stats()
        print(
            f"\n\nStopped after {zstats['done']}/{zstats['total']} ZIPs. "
            f"Progress saved.\n"
            f"Resume with: python main.py --query \"{query}\" "
            f"{'--state ' + label.upper() if len(label) == 2 else '--zips ...'} --resume"
        )
        return csv_path

    duration = time.perf_counter() - start
    totals = tracker.totals()
    zstats = tracker.zip_stats()

    _print_zip_summary(query, label, totals, zstats, duration, csv_path)
    logger.info(
        f"=== ZIP pipeline done: {totals['leads']} leads, "
        f"{zstats['done']} ZIPs done, {zstats['failed']} failed ==="
    )
    return csv_path


def _rebuild_seen_from_csv(csv_path: str) -> Set[str]:
    """Rebuild the deduplication set from an existing CSV so resumes don't add duplicates."""
    seen: Set[str] = set()
    if not os.path.exists(csv_path):
        return seen
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("website", "").lower()
                or f"{row.get('business_name', '')}|{row.get('address', '')}".lower()
            )
            if key:
                seen.add(key)
    return seen


_G = "\033[32m"   # green  — success
_Y = "\033[33m"   # yellow — soft failures / warnings
_R = "\033[31m"   # red    — hard failures
_X = "\033[0m"    # reset


def _print_zip_summary(
    query: str,
    label: str,
    totals: dict,
    zstats: dict,
    duration: float,
    csv_path: str,
) -> None:
    width = 54
    sep = "=" * width
    thin = "-" * width
    total = totals["leads"]

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%" if total else "0.0%"

    def row(label: str, value: str, color: str = _X) -> str:
        return f"  {label:<20}{color}{value}{_X}"

    lines = [
        "",
        sep,
        "  ZIP SCRAPE SUMMARY",
        thin,
        row("Query",          query),
        row("Label",          label),
        row("Duration",       f"{round(duration, 1)}s"),
        thin,
        "  COVERAGE",
        row("ZIPs completed", f"{zstats['done']} / {zstats['total']}", _G),
        row("ZIPs failed",    str(zstats["failed"]),                   _R if zstats["failed"] else _X),
        row("Total leads",    str(total)),
        thin,
        "  EXTRACTION",
        row("Success",        f"{totals.get('success', 0):>4}   {pct(totals.get('success', 0))}",       _G),
        row("No website",     f"{totals.get('no_website', 0):>4}   {pct(totals.get('no_website', 0))}", _Y),
        row("Crawl failed",   f"{totals.get('crawl_failed', 0):>4}   {pct(totals.get('crawl_failed', 0))}", _R),
        row("LLM failed",     f"{totals.get('llm_failed', 0):>4}   {pct(totals.get('llm_failed', 0))}", _R),
        thin,
        f"  Output: {csv_path}",
        sep,
        "",
    ]
    print("\n".join(lines))
