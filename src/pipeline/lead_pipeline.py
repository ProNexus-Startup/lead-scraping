import asyncio
import time
from typing import List, Set

import config.settings as settings
from src.extractors.llm_extractor import extract_owner
from src.models.lead import Lead
from src.scrapers.maps_scraper import search_businesses
from src.scrapers.web_crawler import crawl_domain
from src.utils.csv_writer import write_leads_csv
from src.utils.logger import get_logger
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
        lead.owner_email_primary            = result.get("email_primary")
        lead.owner_email_primary_source     = result.get("email_primary_source_url")
        lead.owner_email_secondary          = result.get("email_secondary")
        lead.owner_email_secondary_source   = result.get("email_secondary_source_url")
        lead.owner_email_other              = result.get("email_other")
        lead.owner_candidates               = result.get("owner_candidates")
        lead.llm_confidence                 = result.get("confidence")
        lead.llm_reasoning                  = result.get("reasoning")

        if lead.owner_name or lead.owner_email_primary:
            lead.status = "success"
            logger.info(
                f"  Found: {lead.owner_name} <{lead.owner_email_primary}> "
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
) -> str:
    """
    ZIP-based pipeline: search each ZIP → deduplicate → Crawl → LLM → single CSV.
    Returns the path to the written CSV file.
    """
    logger.info(
        f"=== ZIP pipeline start: query='{query}' zips={len(zip_codes)} "
        f"limit_per_zip={limit_per_zip} provider={settings.LLM_PROVIDER} ==="
    )

    # Phase 1: collect leads from all ZIPs, deduplicate by website (or name+address)
    all_leads: List[Lead] = []
    seen: Set[str] = set()

    for zip_code in zip_codes:
        zip_query = f"{query} in {zip_code}"
        leads = search_businesses(zip_query, limit=limit_per_zip)
        for lead in leads:
            key = (
                lead.website.lower()
                if lead.website
                else f"{lead.business_name}|{lead.address}".lower()
            )
            if key not in seen:
                seen.add(key)
                all_leads.append(lead)

    if not all_leads:
        logger.warning("No businesses returned from any ZIP. Check your API key and query.")
        return ""

    logger.info(f"Collected {len(all_leads)} unique leads across {len(zip_codes)} ZIPs")

    # Phase 2: crawl + LLM
    model = settings.CEREBRAS_MODEL if settings.LLM_PROVIDER == "cerebras" else settings.GROQ_MODEL
    start = time.perf_counter()

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_LEADS)
    await asyncio.gather(*[_process_lead(lead, semaphore) for lead in all_leads])

    duration = time.perf_counter() - start
    label = output_label or query
    csv_path = write_leads_csv(all_leads, settings.OUTPUT_DIR, label=label)
    write_run_summary(
        leads=all_leads,
        csv_path=csv_path,
        query=query,
        provider=settings.LLM_PROVIDER,
        model=model,
        duration_seconds=duration,
    )

    success_count = sum(1 for l in all_leads if l.status == "success")
    logger.info(
        f"=== ZIP pipeline done: {len(all_leads)} total, {success_count} with owner extracted ==="
    )
    return csv_path
