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
    owner_evidence_text: Optional[str] = None       # exact quote from site identifying the owner
    # Email fields — 4-tier classification
    email_owner_personal: Optional[str] = None      # has owner's name or explicitly linked to owner
    email_owner_personal_source: Optional[str] = None
    email_owner_likely: Optional[str] = None        # probably owner's (biz-name gmail, sole-operator ISP)
    email_owner_likely_source: Optional[str] = None
    email_generic: Optional[str] = None             # info@, contact@, hello@, etc.
    email_generic_source: Optional[str] = None
    email_other: Optional[str] = None               # any remaining emails, comma-separated
    recommended_email: Optional[str] = None         # LLM's best pick for outreach
    recommended_email_type: Optional[str] = None    # owner_personal | owner_likely | generic | other
    owner_candidates: Optional[str] = None          # JSON array of all named candidates when ambiguous
    llm_confidence: Optional[str] = None            # high / medium / low
    llm_reasoning: Optional[str] = None

    # Pipeline metadata
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending | no_website | crawl_failed | llm_failed | success

    def to_csv_row(self) -> dict:
        return {
            "business_name":              self.business_name,
            "business_name_normalized":   self.business_name_normalized or "",
            "category":                   self.category,
            "phone":                      self.phone,
            "address":                    self.address,
            "website":                    self.website,
            "rating":                     self.rating if self.rating is not None else "",
            "reviews_count":              self.reviews_count if self.reviews_count is not None else "",
            "owner_first_name":           self.owner_first_name or "",
            "owner_last_name":            self.owner_last_name or "",
            "owner_name":                 self.owner_name or "",
            "owner_source_page":          self.owner_source_page or "",
            "owner_evidence_text":        self.owner_evidence_text or "",
            "email_owner_personal":       self.email_owner_personal or "",
            "email_owner_personal_source": self.email_owner_personal_source or "",
            "email_owner_likely":         self.email_owner_likely or "",
            "email_owner_likely_source":  self.email_owner_likely_source or "",
            "email_generic":              self.email_generic or "",
            "email_generic_source":       self.email_generic_source or "",
            "email_other":                self.email_other or "",
            "recommended_email":          self.recommended_email or "",
            "recommended_email_type":     self.recommended_email_type or "",
            "owner_candidates":           self.owner_candidates or "",
            "llm_confidence":             self.llm_confidence or "",
            "llm_reasoning":              self.llm_reasoning or "",
            "scraped_at":                 self.scraped_at,
            "status":                     self.status,
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
            "owner_evidence_text",
            "email_owner_personal",
            "email_owner_personal_source",
            "email_owner_likely",
            "email_owner_likely_source",
            "email_generic",
            "email_generic_source",
            "email_other",
            "recommended_email",
            "recommended_email_type",
            "owner_candidates",
            "llm_confidence",
            "llm_reasoning",
            "scraped_at",
            "status",
        ]
