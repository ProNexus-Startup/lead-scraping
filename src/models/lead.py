from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Lead:
    # Google Maps fields
    business_name: str
    category: str
    phone: str
    address: str
    website: str
    rating: Optional[float]
    reviews_count: Optional[int]

    # LLM-extracted fields
    business_name_normalized: Optional[str] = None  # stripped of Inc./LLC/etc. for outreach
    owner_first_name: Optional[str] = None          # first name only, for personalized outreach
    owner_last_name: Optional[str] = None
    owner_name: Optional[str] = None                # full name as seen on site
    owner_source_page: Optional[str] = None
    owner_email_primary: Optional[str] = None       # owner-specific email (john@company.com)
    owner_email_primary_source: Optional[str] = None
    owner_email_secondary: Optional[str] = None     # best generic email (info@, contact@)
    owner_email_secondary_source: Optional[str] = None
    owner_email_other: Optional[str] = None         # any additional emails found, comma-separated
    owner_candidates: Optional[str] = None          # JSON array of all named candidates when ambiguous
    llm_confidence: Optional[str] = None            # high / medium / low
    llm_reasoning: Optional[str] = None

    # Pipeline metadata
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending | no_website | crawl_failed | llm_failed | success

    def to_csv_row(self) -> dict:
        return {
            "business_name": self.business_name,
            "business_name_normalized": self.business_name_normalized or "",
            "category": self.category,
            "phone": self.phone,
            "address": self.address,
            "website": self.website,
            "rating": self.rating if self.rating is not None else "",
            "reviews_count": self.reviews_count if self.reviews_count is not None else "",
            "owner_first_name": self.owner_first_name or "",
            "owner_last_name": self.owner_last_name or "",
            "owner_name": self.owner_name or "",
            "owner_source_page": self.owner_source_page or "",
            "owner_email_primary": self.owner_email_primary or "",
            "owner_email_primary_source": self.owner_email_primary_source or "",
            "owner_email_secondary": self.owner_email_secondary or "",
            "owner_email_secondary_source": self.owner_email_secondary_source or "",
            "owner_email_other": self.owner_email_other or "",
            "owner_candidates": self.owner_candidates or "",
            "llm_confidence": self.llm_confidence or "",
            "llm_reasoning": self.llm_reasoning or "",
            "scraped_at": self.scraped_at,
            "status": self.status,
        }

    @staticmethod
    def csv_fieldnames() -> list[str]:
        return [
            "business_name",
            "business_name_normalized",
            "category",
            "phone",
            "address",
            "website",
            "rating",
            "reviews_count",
            "owner_first_name",
            "owner_last_name",
            "owner_name",
            "owner_source_page",
            "owner_email_primary",
            "owner_email_primary_source",
            "owner_email_secondary",
            "owner_email_secondary_source",
            "owner_email_other",
            "owner_candidates",
            "llm_confidence",
            "llm_reasoning",
            "scraped_at",
            "status",
        ]
