import time
from typing import List, Optional

import requests

import config.settings as settings
from src.models.lead import Lead
from src.utils.logger import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "x-rapidapi-key": settings.RAPIDAPI_KEY,
    "x-rapidapi-host": settings.MAPS_API_HOST,
}


def search_businesses(query: str, limit: int = 20, country: str = "us", lang: str = "en") -> List[Lead]:
    """
    Query the Maps Data API and return a list of partially-populated Lead objects.
    The owner_name / owner_email fields are left empty — filled in later by the pipeline.
    """
    leads: List[Lead] = []
    offset = 0
    fetched = 0

    while fetched < limit:
        batch = min(500, limit - fetched)
        params = {
            "query": query,
            "limit": batch,
            "country": country,
            "lang": lang,
            "offset": offset,
        }
        logger.info(f"Maps API request: query='{query}' offset={offset} batch={batch}")

        try:
            resp = requests.get(
                f"{settings.MAPS_API_BASE_URL}/searchmaps.php",
                headers=_HEADERS,
                params=params,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(f"Maps API request failed: {exc}")
            break

        data = resp.json()
        businesses = _extract_businesses(data)

        if not businesses:
            logger.info("No more results from Maps API.")
            break

        for biz in businesses:
            lead = _business_to_lead(biz)
            if lead:
                leads.append(lead)

        fetched += len(businesses)
        offset += len(businesses)

        if fetched < limit and len(businesses) == batch:
            time.sleep(0.5)

    logger.info(f"Maps scraper returned {len(leads)} businesses for query='{query}'")
    return leads


def _extract_businesses(data: dict) -> list:
    # The API may return results under 'data', 'results', or at the top level as a list
    if isinstance(data, list):
        return data
    for key in ("data", "results", "businesses", "places"):
        if key in data and isinstance(data[key], list):
            return data[key]
    logger.warning(f"Unexpected Maps API response structure. Keys: {list(data.keys())}")
    return []


def _business_to_lead(biz: dict) -> Optional[Lead]:
    name = biz.get("name") or biz.get("title") or ""
    if not name:
        return None

    return Lead(
        business_name=name.strip(),
        category=_first_str(biz, ["category", "type", "types"]),
        phone=_first_str(biz, ["phone", "phone_number", "formatted_phone_number"]),
        address=_first_str(biz, ["address", "full_address", "formatted_address", "vicinity"]),
        website=_clean_url(_first_str(biz, ["website", "url", "web_url"])),
        rating=_safe_float(biz.get("rating")),
        reviews_count=_safe_int(biz.get("reviews") or biz.get("user_ratings_total") or biz.get("review_count")),
    )


def _first_str(biz: dict, keys: list) -> str:
    for k in keys:
        val = biz.get(k)
        if val and isinstance(val, str):
            return val.strip()
        if val and isinstance(val, list) and val:
            return str(val[0]).strip()
    return ""


def _clean_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None
