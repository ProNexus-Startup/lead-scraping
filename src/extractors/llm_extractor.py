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
    if settings.LLM_PROVIDER == "local":
        return AsyncOpenAI(
            api_key="local",
            base_url=settings.LOCAL_LLM_BASE_URL,
        )
    return AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )


_client = _build_client()

# Enforces the exact output shape — no JSON format instructions needed in the prompt.
_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "lead_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "owner_first_name":            {"type": "string"},
                "owner_last_name":             {"type": "string"},
                "owner_name":                  {"type": "string"},
                "owner_source_url":            {"type": "string"},
                "email_primary":               {"type": "string"},
                "email_primary_source_url":    {"type": "string"},
                "email_secondary":             {"type": "string"},
                "email_secondary_source_url":  {"type": "string"},
                "email_other": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "business_name_normalized":    {"type": "string"},
                "owner_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":      {"type": "string"},
                            "role_hint": {"type": "string"},
                        },
                        "required": ["name", "role_hint"],
                        "additionalProperties": False,
                    },
                },
                "confidence": {"type": "string"},
                "reasoning":  {"type": "string"},
            },
            "required": [
                "owner_first_name", "owner_last_name", "owner_name",
                "owner_source_url", "email_primary", "email_primary_source_url",
                "email_secondary", "email_secondary_source_url",
                "email_other", "business_name_normalized", "owner_candidates",
                "confidence", "reasoning",
            ],
            "additionalProperties": False,
        },
    },
}

# This is a TEMPORARY fix for Groq as the strict json schema is not supported on all models.
# Groq only supports json_schema on these specific models; all others get json_object.
_GROQ_JSON_SCHEMA_MODELS = frozenset({
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
})


def _get_response_format(model: str) -> dict:
    """Return json_schema when the provider/model supports it, json_object otherwise."""
    if settings.LLM_PROVIDER == "local":
        return {"type": "json_object"}
    if settings.LLM_PROVIDER == "cerebras":
        return _RESPONSE_SCHEMA
    if model in _GROQ_JSON_SCHEMA_MODELS:
        return _RESPONSE_SCHEMA
    return {"type": "json_object"}


_SYSTEM_PROMPT = """\
You are a senior business intelligence analyst. Your job is to read website content and make \
a confident, well-reasoned judgment about who owns or founded each business — extracting their \
name, contact details, and the evidence behind your conclusion.

--- CONFIDENCE LEVELS ---
Use exactly one of: high, medium, low.

HIGH — The page explicitly uses ownership language about this person. \
Examples: "John Smith, Owner", "Founded by Jane Doe", "Owned and operated by Bob", \
"Meet our founder, Sarah", "President & Owner". The title or role must be directly attached \
to their name on the page.

MEDIUM — Ownership is not stated outright but is strongly implied. Use medium when ANY of \
these apply:
  • The business is named after the person (e.g. "Smith's HVAC" — last name matches).
  • Only one person is named anywhere on the site and the context suggests they run it.
  • The person is introduced as a family member in a clearly family-owned business.
  • The person signs off the "Our Story", "About Us", or similar owner-voice content.
  • A personal email address (firstname@domain.com) matches a name prominently on the site.

LOW — Limited or ambiguous signals. Use low when:
  • Multiple people are named and you cannot determine who owns the business.
  • The person's stated role is not owner (e.g. manager, technician) but they are the \
best available candidate.
  • The first name is inferred only from a personal email address with no other name context.
  • The site has very little information and the identification is a guess.

--- MULTIPLE PEOPLE ---
If multiple people are mentioned and ownership is unclear, pick the single most likely \
candidate as the primary owner (confidence=low) and list ALL candidates in owner_candidates, \
ranked from most likely to least likely to be the owner. Include a brief role_hint for each \
(e.g. "only person named on about page", "listed as lead technician", "mentioned in review").

DO NOT pick names from customer reviews, testimonials, or awards.
DO NOT return brand names, product names, or award titles as owner names.

--- BUSINESS NAME NORMALIZATION ---
Remove legal suffixes (Inc., LLC, Co., Ltd., Corp., LLP, PLLC, etc.) and produce a clean \
short name for email outreach. Example: "Besco Air Inc." → "Besco Air".

--- EMAIL HIERARCHY ---
Collect every email address you find on the site, then assign them as follows:
  • email_primary: the owner's personal email (e.g. john@company.com, firstname@domain.com). \
This is the highest priority — a direct line to the owner.
  • email_secondary: the best generic contact email found (info@, contact@, hello@, \
service@, team@, office@, etc.).
  • email_other: a list of any remaining email addresses found (other generic or departmental \
emails). Use an empty array [] if none remain.
Use empty string for email_primary and email_secondary if not found.

--- OWNER NAME ---
IMPORTANT — owner_first_name must contain ONLY the first name. Do not include a middle \
initial, middle name, or last name. This field is used to address the owner directly in \
outreach emails ("Hi John,") so it must be just one given name.
  • owner_first_name: first name only. No middle initial. No last name. (e.g. "John" not "John A." or "John Smith")
  • owner_last_name: last name only.
  • owner_name: full name exactly as it appears on the site.
Use empty string for any name field you cannot determine.

--- SOURCE URLS ---
Return the exact URL from the [PAGE: <url>] header where you found each piece of information. \
Use empty string if not found.
"""

_USER_TEMPLATE = """\
Business website: {url}

Website content (each section starts with [PAGE: <url>]):
{text}

---
Extract the following from the website content above:
1. The owner, founder, or principal of this business — not a manager, employee, \
receptionist, customer, reviewer, or award recipient.
2. Their first name ONLY for outreach (no middle initial or last name), their last name, \
and their full name as seen on the site.
3. A normalized business name with legal suffixes removed (for use in outreach emails).
4. ALL email addresses found on the site, assigned to the correct tier: \
owner-specific email as primary, best generic email as secondary, remaining emails in other.
5. The source page URL where you found the owner name, and where you found the email.
6. If multiple people are mentioned but ownership is unclear, list ALL of them in \
owner_candidates ranked from most to least likely to be the owner.
7. Your confidence level (high / medium / low) and one sentence of reasoning.

Respond with a JSON object using EXACTLY these field names:
owner_first_name, owner_last_name, owner_name, owner_source_url,
email_primary, email_primary_source_url, email_secondary, email_secondary_source_url,
email_other (array of strings), business_name_normalized,
owner_candidates (array of objects with "name" and "role_hint" keys),
confidence, reasoning
"""


async def extract_owner(website_url: str, page_text: str) -> dict:
    if not page_text.strip():
        return _empty_result("no page text")

    if settings.LLM_PROVIDER == "cerebras":
        model = settings.CEREBRAS_MODEL
    elif settings.LLM_PROVIDER == "local":
        model = settings.LOCAL_LLM_MODEL
    else:
        model = settings.GROQ_MODEL
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _USER_TEMPLATE.format(url=website_url, text=page_text[:15_000])},
    ]

    try:
        raw = await _call_with_retry(messages, model, website_url)
        logger.debug(f"LLM raw response for {website_url}: {raw}")
        return _parse_response(raw, website_url)
    except Exception as exc:
        logger.error(f"LLM extraction failed for {website_url}: {exc}")
        return _empty_result(str(exc))


async def _call_with_retry(messages: list, model: str, website_url: str) -> str:
    for attempt in range(2):
        try:
            extra = {"chat_template_kwargs": {"enable_thinking": False}} if settings.LLM_PROVIDER == "local" else {}
            response = await _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=3000,
                response_format=_get_response_format(model),
                extra_body=extra,
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("Empty response from model")
            return content.strip()
        except RateLimitError as exc:
            if attempt == 1:
                raise
            wait = _parse_retry_wait(str(exc))
            logger.warning(f"Rate limit hit for {website_url}. Retrying in {wait}s.")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")


def _parse_retry_wait(error_message: str, default: float = 10.0) -> float:
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", error_message, re.IGNORECASE)
    return float(match.group(1)) + 0.5 if match else default


def _parse_response(raw: str, website_url: str = "") -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback in case a provider ignores response_format
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse LLM JSON for {website_url}: {raw[:200]}")
                return _empty_result("json_parse_error")
        else:
            return _empty_result("no_json_found")

    owner_first = _clean_name(parsed.get("owner_first_name"))
    owner_last = _clean_name(parsed.get("owner_last_name"))
    owner_full = _clean_name(parsed.get("owner_name"))
    email_primary = _validate_email(parsed.get("email_primary"))
    email_secondary = _validate_email(parsed.get("email_secondary"))

    # Infer first name from personal email if the LLM couldn't find one
    if not owner_first and email_primary:
        owner_first = _infer_first_name_from_email(email_primary)

    # Collect and validate any remaining emails
    email_other_raw = parsed.get("email_other") or []
    email_other_valid = [e for e in (
        _validate_email(e) for e in email_other_raw if isinstance(e, str)
    ) if e]
    email_other = ", ".join(email_other_valid) if email_other_valid else None

    candidates_raw = parsed.get("owner_candidates") or []
    candidates_json = json.dumps(candidates_raw) if candidates_raw else None

    return {
        "owner_first_name":           owner_first,
        "owner_last_name":            owner_last,
        "owner_name":                 owner_full,
        "owner_source_url":           _clean_url(parsed.get("owner_source_url")),
        "email_primary":              email_primary,
        "email_primary_source_url":   _clean_url(parsed.get("email_primary_source_url")),
        "email_secondary":            email_secondary,
        "email_secondary_source_url": _clean_url(parsed.get("email_secondary_source_url")),
        "email_other":                email_other,
        "business_name_normalized":   _clean_name(parsed.get("business_name_normalized")),
        "owner_candidates":           candidates_json,
        "confidence":                 parsed.get("confidence") or "low",
        "reasoning":                  parsed.get("reasoning") or "",
    }


_SENTINEL_STRINGS = frozenset({
    "null", "none", "n/a", "unknown", "not found", "not available", "first last",
    "<full name>", "<first name>", "<last name>", "<email address>", "<source page url>", "",
})

_GENERIC_EMAIL_PREFIXES = frozenset({
    "info", "contact", "hello", "hi", "mail", "email", "support",
    "admin", "office", "team", "sales", "help", "service", "enquiries",
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


def _infer_first_name_from_email(email: str) -> Optional[str]:
    """Infer a first name from a personal email address"""
    local = email.split("@")[0].lower()
    if local in _GENERIC_EMAIL_PREFIXES:
        return None
    name_part = re.split(r"[._\d]", local)[0]
    if len(name_part) >= 3 and name_part.isalpha():
        return name_part.capitalize()
    return None


def _empty_result(reason: str) -> dict:
    return {
        "owner_first_name":           None,
        "owner_last_name":            None,
        "owner_name":                 None,
        "owner_source_url":           None,
        "email_primary":              None,
        "email_primary_source_url":   None,
        "email_secondary":            None,
        "email_secondary_source_url": None,
        "email_other":                None,
        "business_name_normalized":   None,
        "owner_candidates":           None,
        "confidence":                 "low",
        "reasoning":                  reason,
    }
