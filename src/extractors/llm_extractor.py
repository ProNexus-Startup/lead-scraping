import json
import re
from typing import Optional

from groq import Groq

import config.settings as settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_client = Groq(api_key=settings.GROQ_API_KEY)

_SYSTEM_PROMPT = """\
You are a business intelligence assistant. Your job is to read website text and identify the most likely business owner, founder, or principal — not a manager, employee, or receptionist.

Return ONLY a valid JSON object. No markdown, no explanation, just JSON.
"""

_USER_TEMPLATE = """\
Business website: {url}

Website content:
{text}

---
Identify:
1. The most likely owner, founder, or principal of this business.
2. The best contact email (owner's direct email preferred; generic like info@, contact@, hello@ are acceptable if no personal email is found).

Return exactly this JSON structure:
{{"owner_name": "Full Name or null", "email": "email@domain.com or null", "confidence": "high|medium|low", "reasoning": "one sentence"}}
"""


def extract_owner(website_url: str, page_text: str) -> dict:
    """
    Calls the Groq LLM and returns a dict with keys:
      owner_name, email, confidence, reasoning
    All values may be None if not found.
    """
    if not page_text.strip():
        return _empty_result("no page text")

    prompt = _USER_TEMPLATE.format(url=website_url, text=page_text[:40_000])

    try:
        response = _client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        logger.debug(f"LLM raw response for {website_url}: {raw}")
        return _parse_response(raw)
    except Exception as exc:
        logger.error(f"LLM extraction failed for {website_url}: {exc}")
        return _empty_result(str(exc))


def _parse_response(raw: str) -> dict:
    # Strip markdown code fences if the model adds them
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting the first {...} block as a fallback
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
        "owner_name": parsed.get("owner_name") or None,
        "email": _validate_email(parsed.get("email")),
        "confidence": parsed.get("confidence") or "low",
        "reasoning": parsed.get("reasoning") or "",
    }


def _validate_email(email: Optional[str]) -> Optional[str]:
    if not email or not isinstance(email, str):
        return None
    email = email.strip().lower()
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return email
    return None


def _empty_result(reason: str) -> dict:
    return {"owner_name": None, "email": None, "confidence": "low", "reasoning": reason}
