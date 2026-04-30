import asyncio
import json
import re
from typing import Optional

from openai import AsyncOpenAI, RateLimitError

import config.settings as settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _build_client() -> AsyncOpenAI:
    if settings.LLM_PROVIDER == "cerebras":
        return AsyncOpenAI(
            api_key=settings.CEREBRAS_API_KEY,
            base_url="https://api.cerebras.ai/v1",
        )
    return AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )


_client = _build_client()

_SYSTEM_PROMPT = """\
You are a business intelligence assistant. Your job is to read website text and identify \
the business owner, founder, or principal — the person who owns or founded the company.

Rules:
- Only identify someone who is explicitly or strongly implied to be the owner or founder.
- Do NOT pick names from customer reviews, testimonials, or awards.
- Do NOT return brand names, product names, or award titles as owner names.
- If you cannot identify the owner with reasonable certainty, return null for owner_name.
- Confidence levels: high = explicitly named as owner/founder on the site. \
medium = strongly implied (e.g. named family member in a family-owned business). \
low = best guess from limited information.

Return ONLY a valid JSON object. No markdown, no explanation, just JSON.
All field values must be clean data — no qualifiers, notes, or uncertainty markers.
For source URLs, return the exact URL from the [PAGE: <url>] header where you found \
the information, or null if not found.
"""

_USER_TEMPLATE = """\
Business website: {url}

Website content (each section starts with [PAGE: <url>]):
{text}

---
Identify:
1. The owner, founder, or principal of this business — not a manager, employee, \
receptionist, customer, reviewer, or award recipient.
2. The best contact email (owner's direct email preferred; generic info@, contact@, \
hello@ are acceptable if no personal email found).
3. For each piece of information, note the [PAGE: <url>] it came from.

Return exactly this JSON structure (use null for any field you cannot determine):
{{"owner_name": "<full name>", "owner_source_url": "<source page url>", \
"email": "<email address>", "email_source_url": "<source page url>", \
"confidence": "high|medium|low", \
"reasoning": "<one sentence explaining why this person is the owner>"}}
"""


async def extract_owner(website_url: str, page_text: str) -> dict:
    """Calls the configured LLM provider and returns owner_name, email, confidence, reasoning."""
    if not page_text.strip():
        return _empty_result("no page text")

    model = settings.CEREBRAS_MODEL if settings.LLM_PROVIDER == "cerebras" else settings.GROQ_MODEL
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _USER_TEMPLATE.format(url=website_url, text=page_text[:40_000])},
    ]

    try:
        raw = await _call_with_retry(messages, model, website_url)
        logger.debug(f"LLM raw response for {website_url}: {raw}")
        return _parse_response(raw)
    except Exception as exc:
        logger.error(f"LLM extraction failed for {website_url}: {exc}")
        return _empty_result(str(exc))


async def _call_with_retry(messages: list, model: str, website_url: str) -> str:
    """Makes the LLM API call with a single retry on rate limit errors."""
    for attempt in range(2):
        try:
            response = await _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except RateLimitError as exc:
            if attempt == 1:
                raise
            wait = _parse_retry_wait(str(exc))
            logger.warning(f"Rate limit hit for {website_url}. Retrying in {wait}s.")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # both attempts exhausted above


def _parse_retry_wait(error_message: str, default: float = 10.0) -> float:
    """Extracts the suggested wait time from a rate limit error message."""
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", error_message, re.IGNORECASE)
    return float(match.group(1)) + 0.5 if match else default


def _parse_response(raw: str) -> dict:
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse LLM JSON: {raw[:200]}")
                return _empty_result("json_parse_error")
        else:
            return _empty_result("no_json_found")

    return {
        "owner_name": _clean_name(parsed.get("owner_name")),
        "owner_source_url": _clean_url(parsed.get("owner_source_url")),
        "email": _validate_email(parsed.get("email")),
        "email_source_url": _clean_url(parsed.get("email_source_url")),
        "confidence": parsed.get("confidence") or "low",
        "reasoning": parsed.get("reasoning") or "",
    }


_SENTINEL_STRINGS = frozenset({
    "null", "none", "n/a", "unknown", "not found", "not available", "first last",
    "<full name>", "<email address>", "<source page url>", "",
})


def _clean_name(name: Optional[str]) -> Optional[str]:
    if not name or not isinstance(name, str):
        return None
    name = re.sub(r"\s*\(.*?\)", "", name).strip()
    if name.lower() in _SENTINEL_STRINGS:
        return None
    return name or None


def _validate_email(email: Optional[str]) -> Optional[str]:
    if not email or not isinstance(email, str):
        return None
    email = email.strip().lower()
    if email in _SENTINEL_STRINGS:
        return None
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return email
    return None


def _clean_url(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.lower() in _SENTINEL_STRINGS:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return None


def _empty_result(reason: str) -> dict:
    return {
        "owner_name": None,
        "owner_source_url": None,
        "email": None,
        "email_source_url": None,
        "confidence": "low",
        "reasoning": reason,
    }
