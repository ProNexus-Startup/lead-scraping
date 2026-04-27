"""
Unit tests for llm_extractor parsing logic (no Groq API calls).
Run: python -m pytest tests/
"""

import unittest
from unittest.mock import patch, MagicMock


class TestLLMExtractorParsing(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(
            "os.environ",
            {"RAPIDAPI_KEY": "test", "GROQ_API_KEY": "test"},
        )
        self.env_patch.start()
        # Patch Groq client so importing the module doesn't make real connections
        self.groq_patch = patch("groq.Groq")
        self.groq_patch.start()
        from src.extractors.llm_extractor import _parse_response, _validate_email, _empty_result
        self._parse_response = _parse_response
        self._validate_email = _validate_email
        self._empty_result = _empty_result

    def tearDown(self):
        self.groq_patch.stop()
        self.env_patch.stop()

    def test_valid_json_parsed(self):
        raw = '{"owner_name": "Jane Doe", "email": "jane@example.com", "confidence": "high", "reasoning": "Found on about page"}'
        result = self._parse_response(raw)
        self.assertEqual(result["owner_name"], "Jane Doe")
        self.assertEqual(result["email"], "jane@example.com")
        self.assertEqual(result["confidence"], "high")

    def test_json_in_markdown_fences(self):
        raw = '```json\n{"owner_name": "Bob", "email": "bob@shop.com", "confidence": "medium", "reasoning": "bio"}\n```'
        result = self._parse_response(raw)
        self.assertEqual(result["owner_name"], "Bob")

    def test_null_fields_become_none(self):
        raw = '{"owner_name": null, "email": null, "confidence": "low", "reasoning": "no info"}'
        result = self._parse_response(raw)
        self.assertIsNone(result["owner_name"])
        self.assertIsNone(result["email"])

    def test_invalid_email_rejected(self):
        result = self._validate_email("not-an-email")
        self.assertIsNone(result)

    def test_valid_email_accepted(self):
        result = self._validate_email("info@mybusiness.com")
        self.assertEqual(result, "info@mybusiness.com")

    def test_email_lowercased(self):
        result = self._validate_email("Owner@EXAMPLE.COM")
        self.assertEqual(result, "owner@example.com")


if __name__ == "__main__":
    unittest.main()
