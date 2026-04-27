from typing import List, Optional

import config.settings as settings
from src.extractors.llm_extractor import extract_owner
from src.models.lead import Lead
from src.scrapers.maps_scraper import search_businesses
from src.scrapers.web_crawler import crawl_domain
from src.utils.csv_writer import write_leads_csv
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run(query: str, limit: int = 1, output_label: str = "") -> str:
    """
    Full pipeline: Maps → Crawl → LLM → CSV.
    Returns the path to the written CSV file.
    """
    logger.info(f"=== Pipeline start: query='{query}' limit={limit} ===")

    leads = search_businesses(query, limit=limit)
    if not leads:
        logger.warning("No businesses returned from Maps API. Check your API key and query.")
        return ""

    for i, lead in enumerate(leads, 1):
        logger.info(f"[{i}/{len(leads)}] Processing: {lead.business_name}")
        _process_lead(lead)

    label = output_label or query
    csv_path = write_leads_csv(leads, settings.OUTPUT_DIR, label=label)

    success_count = sum(1 for l in leads if l.status == "success")
    logger.info(
        f"=== Pipeline done: {len(leads)} total, {success_count} with owner extracted ==="
    )
    return csv_path


def _process_lead(lead: Lead) -> None:
    if not lead.website:
        lead.status = "no_website"
        logger.info(f"  No website for {lead.business_name}")
        return

    logger.info(f"  Crawling {lead.website}")
    try:
        page_text = crawl_domain(lead.website)
    except Exception as exc:
        logger.error(f"  Crawl error for {lead.website}: {exc}")
        lead.status = "crawl_failed"
        return

    if not page_text:
        lead.status = "crawl_failed"
        logger.warning(f"  No text extracted from {lead.website}")
        return

    logger.info(f"  Running LLM extraction for {lead.website}")
    result = extract_owner(lead.website, page_text)

    lead.owner_name = result.get("owner_name")
    lead.owner_email = result.get("email")
    lead.llm_confidence = result.get("confidence")

    if lead.owner_name or lead.owner_email:
        lead.status = "success"
        logger.info(f"  Found: {lead.owner_name} <{lead.owner_email}> (confidence={lead.llm_confidence})")
    else:
        lead.status = "llm_failed"
        logger.info(f"  LLM could not identify owner. Reason: {result.get('reasoning')}")
