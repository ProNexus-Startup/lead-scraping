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
                "owner_first_name":             {"type": "string"},
                "owner_last_name":              {"type": "string"},
                "owner_name":                   {"type": "string"},
                "owner_source_url":             {"type": "string"},
                "owner_evidence_text":          {"type": "string"},
                "email_owner_personal":         {"type": "string"},
                "email_owner_personal_source":  {"type": "string"},
                "email_owner_likely":           {"type": "string"},
                "email_owner_likely_source":    {"type": "string"},
                "email_generic":                {"type": "string"},
                "email_generic_source":         {"type": "string"},
                "email_other": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_email":            {"type": "string"},
                "recommended_email_type":       {"type": "string"},
                "business_name_normalized":     {"type": "string"},
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
                "owner_source_url", "owner_evidence_text",
                "email_owner_personal", "email_owner_personal_source",
                "email_owner_likely", "email_owner_likely_source",
                "email_generic", "email_generic_source",
                "email_other", "recommended_email", "recommended_email_type",
                "business_name_normalized", "owner_candidates",
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
You are a senior business intelligence analyst. Your task is to extract owner contact data \
from small business websites for outreach campaigns. Accuracy in field assignment matters \
more than completeness — a wrong assignment is worse than an empty field.

---

## SECTION 1: OWNER IDENTIFICATION

Identify the single most likely owner, founder, or principal. Use this priority order:

1. Person with explicit ownership language directly attached to their name on the page \
("Owner", "Founded by", "Owned and operated by", "President & Owner", "Meet our founder")
2. Person whose last name matches the business name (e.g. "Smith's HVAC" → last name Smith)
3. Only person named on the site in an owner-voice context (About Us, Our Story, signed letter)
4. Best available candidate when none of the above apply (confidence = low)

MUST NOT pick: customers, reviewers, award recipients, brand names, product names, \
employees whose stated role is not owner (manager, technician, receptionist).

**Confidence — use exactly one of: high, medium, low**

HIGH — Explicit ownership language is directly attached to this person's name on the page. \
The title or role must appear next to or immediately describing the name — not inferred from context.
Qualifying examples:
  • "John Smith, Owner"  |  "Founded by Jane Doe"  |  "Owned and operated by Bob"
  • "Meet our founder, Sarah"  |  "President & Owner: Mike Jones"
  • A photo caption reading "Jane Doe — Owner"
Do NOT assign high if ownership language appears on the page but is not tied to a specific name, \
or if you inferred the ownership role from surrounding context.

MEDIUM — Ownership is not stated outright but is clearly implied by the page. \
Assign medium when ANY of these apply:
  • The business name contains this person's name \
(e.g. "Smith's Plumbing" and the person's last name is Smith)
  • Only one person is named anywhere on the site and the context places them as the operator \
(sole About page, signed letter, the only first-person "I" voice on the site)
  • The person is introduced as a family member in a clearly family-run business
  • The person signs off an About Us, Our Story, or owner-voice section — \
even without the word "owner" appearing
  • A personal email (firstname@domain.com or name@gmail.com) matches a name \
prominently featured on the site
  • The business is a sole proprietorship by all signals and one person is introduced by full name

LOW — Signals are limited, ambiguous, or the identification is a best guess. \
Assign low when:
  • Multiple people are named and you cannot clearly determine who owns the business
  • The person's stated role is NOT owner (manager, lead technician, office coordinator) \
but they are the best available candidate
  • The first name was inferred solely from an email address with no other name context on the page
  • The site has very little content and ownership is a guess
  • You chose a candidate mainly because no one else was named, not because of positive evidence

Distribution note: Most small trades businesses that name anyone at all should be MEDIUM or HIGH. \
Do not default to LOW out of caution — if you found the owner with good evidence, use the right level.

**Name fields:**
- `owner_first_name`: First name ONLY. No middle initial. No last name. \
Used for "Hi [first_name]," in outreach. (e.g. "John" not "John A." or "John Smith")
- `owner_last_name`: Last name only.
- `owner_name`: Full name exactly as it appears on the site.
- `owner_source_url`: Exact URL from the [PAGE: <url>] header where the owner name was found.
- `owner_evidence_text`: The exact sentence or short phrase from the page that identifies \
this person as the owner. Quote it verbatim. Empty string if not found.

**Multiple candidates:** If ownership is unclear, pick the most likely as primary \
(confidence = low) and list ALL candidates in `owner_candidates` ranked most to least likely, \
each with a `name` and `role_hint`.

---

## SECTION 2: EMAIL CLASSIFICATION

Collect every email address found on the site. Assign each to exactly one category. \
Use empty string `""` for any category where no qualifying email exists.

**Category 1 — `email_owner_personal` (highest outreach value)**
An email directly linked to the identified owner:
- Contains their first or last name in the local part (e.g. `john@company.com`, \
`jsmith@domain.com`)
- Explicitly labeled as the owner's contact on the page
- A personal consumer/ISP email (gmail.com, yahoo.com, aol.com, hotmail.com, verizon.net, \
comcast.net, bellsouth.net, att.net) on a clearly single-person-operated business

**Category 2 — `email_owner_likely`**
Probably reaches the owner but not personally named:
- Business-name Gmail/Yahoo/consumer email on a sole-operator business \
(e.g. `smithsplumbing@gmail.com`)
- Short non-generic local part on a custom domain (e.g. `rob@company.com`, `s@company.com`)
- Personal ISP email not matching a known name but on a sole-operator site

**Category 3 — `email_generic`**
Clearly a shared/departmental inbox. Local part is one of: info, contact, hello, hi, mail, \
support, admin, office, team, sales, help, service, enquiries, bookings, appointments, \
estimates, quotes, noreply, no-reply, webmaster, customerservice.

**Category 4 — `email_other`**
Any remaining emails that do not fit the above three. Return as an array of strings.

**`recommended_email` — best email for owner outreach**

After classifying all emails, select the single address most likely to reach the owner \
directly when sent a cold outreach message. This is a judgment call — weigh all of these:

1. Does the email contain or match the owner's name? That is the strongest signal it reaches them.
2. Is it from a personal provider (gmail.com, yahoo.com, aol.com, hotmail.com, verizon.net, \
bellsouth.net, comcast.net, att.net)? On a small business, a personal provider almost always \
means the owner's own inbox — not a shared company account.
3. Is this clearly a one-person operation or a larger staffed business? \
For a sole operator, any email likely reaches the owner directly. \
For a multi-employee company, a named or personal email is far more valuable than a generic inbox.
4. Where was the email found? An email on the Contact, About, or Meet the Team page \
is more likely owner-monitored than one buried in a footer or fine print.
5. If two emails seem equally good, prefer the one more likely to be actively checked \
(e.g. a Gmail over an old ISP address; a named email over an anonymous one).

- `recommended_email`: The single best email for outreach. Empty string if no email found at all.
- `recommended_email_type`: The category of the chosen email — exactly one of \
`"owner_personal"`, `"owner_likely"`, `"generic"`, `"other"`, or `""` if no email found.

For each email category, also return the source page URL (from the [PAGE: <url>] header). \
Use empty string if not found.

---

## SECTION 3: BUSINESS NAME

`business_name_normalized`: Remove legal suffixes (Inc., LLC, Co., Ltd., Corp., LLP, PLLC) \
for clean outreach copy. Example: "Besco Air Inc." → "Besco Air".

---

## OUTPUT RULES

- Use empty string `""` for any unfound string field. NEVER return null, "N/A", "unknown", \
"not found", "not available", or placeholder text like "<name>" or "First Last".
- Use empty array `[]` for `email_other` and `owner_candidates` if none found.
- `reasoning`: One sentence explaining your owner identification decision.
"""

_USER_TEMPLATE = """\
Business website: {url}

Website content (each section starts with [PAGE: <url>]):
{text}

---
Extract all required fields following the rules in your instructions.

Respond with a JSON object using EXACTLY these field names:
owner_first_name, owner_last_name, owner_name, owner_source_url, owner_evidence_text,
email_owner_personal, email_owner_personal_source,
email_owner_likely, email_owner_likely_source,
email_generic, email_generic_source,
email_other (array of strings),
recommended_email, recommended_email_type,
business_name_normalized,
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
        {"role": "user", "content": _USER_TEMPLATE.format(url=website_url, text=page_text)},
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
    owner_last  = _clean_name(parsed.get("owner_last_name"))
    owner_full  = _clean_name(parsed.get("owner_name"))

    email_owner_personal = _validate_email(parsed.get("email_owner_personal"))
    email_owner_likely   = _validate_email(parsed.get("email_owner_likely"))
    email_generic        = _validate_email(parsed.get("email_generic"))
    recommended_email    = _validate_email(parsed.get("recommended_email"))

    # Infer first name from owner email if the LLM couldn't find a name
    if not owner_first:
        for e in (email_owner_personal, email_owner_likely):
            if e:
                owner_first = _infer_first_name_from_email(e)
                break

    # Collect and validate any remaining emails
    email_other_raw   = parsed.get("email_other") or []
    email_other_valid = [e for e in (
        _validate_email(e) for e in email_other_raw if isinstance(e, str)
    ) if e]
    email_other = ", ".join(email_other_valid) if email_other_valid else None

    candidates_raw  = parsed.get("owner_candidates") or []
    candidates_json = json.dumps(candidates_raw) if candidates_raw else None

    _VALID_REC_TYPES = {"owner_personal", "owner_likely", "generic", "other", ""}
    rec_type = str(parsed.get("recommended_email_type") or "").strip().lower()
    if rec_type not in _VALID_REC_TYPES:
        rec_type = ""

    return {
        "owner_first_name":            owner_first,
        "owner_last_name":             owner_last,
        "owner_name":                  owner_full,
        "owner_source_url":            _clean_url(parsed.get("owner_source_url")),
        "owner_evidence_text":         _clean_text(parsed.get("owner_evidence_text")),
        "email_owner_personal":        email_owner_personal,
        "email_owner_personal_source": _clean_url(parsed.get("email_owner_personal_source")),
        "email_owner_likely":          email_owner_likely,
        "email_owner_likely_source":   _clean_url(parsed.get("email_owner_likely_source")),
        "email_generic":               email_generic,
        "email_generic_source":        _clean_url(parsed.get("email_generic_source")),
        "email_other":                 email_other,
        "recommended_email":           recommended_email,
        "recommended_email_type":      rec_type or None,
        "business_name_normalized":    _clean_name(parsed.get("business_name_normalized")),
        "owner_candidates":            candidates_json,
        "confidence":                  parsed.get("confidence") or "low",
        "reasoning":                   parsed.get("reasoning") or "",
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


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if text.lower() in _SENTINEL_STRINGS:
        return None
    return text or None


def _empty_result(reason: str) -> dict:
    return {
        "owner_first_name":            None,
        "owner_last_name":             None,
        "owner_name":                  None,
        "owner_source_url":            None,
        "owner_evidence_text":         None,
        "email_owner_personal":        None,
        "email_owner_personal_source": None,
        "email_owner_likely":          None,
        "email_owner_likely_source":   None,
        "email_generic":               None,
        "email_generic_source":        None,
        "email_other":                 None,
        "recommended_email":           None,
        "recommended_email_type":      None,
        "business_name_normalized":    None,
        "owner_candidates":            None,
        "confidence":                  "low",
        "reasoning":                   reason,
    }
