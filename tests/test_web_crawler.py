"""
Unit tests for web_crawler helpers (no network calls).
Run: python -m pytest tests/
"""

import unittest
from unittest.mock import patch


class TestWebCrawlerHelpers(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(
            "os.environ",
            {"RAPIDAPI_KEY": "test", "GROQ_API_KEY": "test"},
        )
        self.env_patch.start()
        from src.scrapers.web_crawler import _normalize_url, _extract_text
        self._normalize_url = _normalize_url
        self._extract_text = _extract_text

    def tearDown(self):
        self.env_patch.stop()

    def test_normalize_url_strips_fragment(self):
        result = self._normalize_url("https://example.com/page#section")
        self.assertNotIn("#", result)

    def test_normalize_url_lowercases_domain(self):
        result = self._normalize_url("https://EXAMPLE.COM/Page")
        self.assertIn("example.com", result)

    def test_normalize_url_strips_trailing_slash(self):
        result = self._normalize_url("https://example.com/about/")
        self.assertFalse(result.endswith("/about/"))

    def test_extract_text_strips_scripts(self):
        html = "<html><body><script>alert(1)</script><p>Hello world</p></body></html>"
        text = self._extract_text(html)
        self.assertIn("Hello world", text)
        self.assertNotIn("alert", text)

    def test_extract_text_strips_nav(self):
        html = "<html><body><nav>Menu items</nav><main>Main content</main></body></html>"
        text = self._extract_text(html)
        self.assertNotIn("Menu items", text)
        self.assertIn("Main content", text)


if __name__ == "__main__":
    unittest.main()
