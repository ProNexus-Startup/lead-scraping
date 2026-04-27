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
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    llm_confidence: Optional[str] = None  # high / medium / low

    # Pipeline metadata
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending | no_website | crawl_failed | llm_failed | success

    def to_csv_row(self) -> dict:
        return {
            "business_name": self.business_name,
            "category": self.category,
            "phone": self.phone,
            "address": self.address,
            "website": self.website,
            "rating": self.rating if self.rating is not None else "",
            "reviews_count": self.reviews_count if self.reviews_count is not None else "",
            "owner_name": self.owner_name or "",
            "owner_email": self.owner_email or "",
            "llm_confidence": self.llm_confidence or "",
            "scraped_at": self.scraped_at,
            "status": self.status,
        }

    @staticmethod
    def csv_fieldnames() -> list[str]:
        return [
            "business_name",
            "category",
            "phone",
            "address",
            "website",
            "rating",
            "reviews_count",
            "owner_name",
            "owner_email",
            "llm_confidence",
            "scraped_at",
            "status",
        ]
