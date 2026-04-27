"""
Unit tests for maps_scraper helpers (no network calls).
Run: python -m pytest tests/
"""

import unittest
from unittest.mock import MagicMock, patch


class TestBusinessToLead(unittest.TestCase):
    def setUp(self):
        # Patch settings before importing the module
        self.settings_patch = patch.dict(
            "os.environ",
            {"RAPIDAPI_KEY": "test", "GROQ_API_KEY": "test"},
        )
        self.settings_patch.start()
        from src.scrapers.maps_scraper import _business_to_lead, _extract_businesses
        self._business_to_lead = _business_to_lead
        self._extract_businesses = _extract_businesses

    def tearDown(self):
        self.settings_patch.stop()

    def test_standard_fields(self):
        biz = {
            "name": "Joe's Plumbing",
            "phone": "+1 512-555-0100",
            "website": "https://joesplumbing.com",
            "address": "123 Main St, Austin, TX 78701",
            "rating": "4.8",
            "reviews": "142",
            "category": "Plumber",
        }
        lead = self._business_to_lead(biz)
        self.assertIsNotNone(lead)
        self.assertEqual(lead.business_name, "Joe's Plumbing")
        self.assertAlmostEqual(lead.rating, 4.8)
        self.assertEqual(lead.reviews_count, 142)

    def test_missing_name_returns_none(self):
        lead = self._business_to_lead({"phone": "555-0100"})
        self.assertIsNone(lead)

    def test_url_without_scheme_gets_https(self):
        biz = {"name": "ACME HVAC", "website": "acmehvac.com"}
        lead = self._business_to_lead(biz)
        self.assertEqual(lead.website, "https://acmehvac.com")

    def test_extract_businesses_from_data_key(self):
        payload = {"data": [{"name": "A"}, {"name": "B"}]}
        result = self._extract_businesses(payload)
        self.assertEqual(len(result), 2)

    def test_extract_businesses_bare_list(self):
        payload = [{"name": "A"}]
        result = self._extract_businesses(payload)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
