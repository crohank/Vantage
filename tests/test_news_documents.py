import os
import sys
import unittest
from unittest.mock import patch


BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..", "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from agents.news_agent import news_agent  # noqa: E402
from get_document_preview import build_preview  # noqa: E402


class FakeDocumentStore:
    def __init__(self, *args, **kwargs):
        pass


class NewsDocumentTests(unittest.TestCase):
    @patch("get_document_preview.DocumentStore", FakeDocumentStore)
    def test_build_preview_uses_saved_news_summary(self):
        preview = build_preview({
            "id": "doc-1",
            "ticker": "AAPL",
            "source_type": "news_article",
            "summary_text": "Apple supplier disruption could pressure margins near term.",
            "impact_reasoning": "The article points to cost and delivery risk ahead of a major product cycle.",
        })

        self.assertEqual(preview["document_id"], "doc-1")
        self.assertIn("supplier disruption", preview["preview_text"])
        self.assertIn("Why it matters", preview["preview_text"])

    @patch("services.news_service.fetch_company_news")
    @patch("services.document_registry.register_document")
    @patch("services.llm_service.get_gemini_service")
    def test_news_agent_creates_source_documents(self, mock_gemini_service, mock_register_document, mock_fetch_company_news):
        mock_fetch_company_news.return_value = {
            "provider": "gnews",
            "available": True,
            "error": None,
            "query": '"Apple Inc." OR AAPL',
            "total_articles": 1,
            "articles": [{
                "title": "Apple expands AI investment",
                "description": "Apple announced a larger AI infrastructure spend.",
                "content": "Management expects the investment to support product growth.",
                "url": "https://example.com/apple-ai",
                "published_at": "2026-04-27T12:00:00+00:00",
                "source_name": "Example News",
                "source_url": "https://example.com",
            }],
        }
        mock_gemini_service.return_value.invoke_json.return_value = {
            "overall_summary": "Recent coverage is mildly positive because management is investing in future growth.",
            "articles": [{
                "article_number": 1,
                "summary": "Apple's new AI spending could improve product competitiveness, though it may lift near-term costs.",
                "impact_direction": "positive",
                "impact_score": 3,
                "reasoning": "The spending can support revenue growth if execution is strong.",
            }],
        }
        mock_register_document.side_effect = lambda entry: {**entry, "id": "news-doc-1"}

        state = {
            "ticker": "AAPL",
            "market_data": {"valuation": {"company_name": "Apple Inc."}},
            "document_sources": [],
            "_analysis_id": "analysis-1",
        }

        result = news_agent(state)

        self.assertIn("news_analysis", result)
        self.assertTrue(result["news_analysis"]["available"])
        self.assertEqual(result["news_analysis"]["material_article_count"], 1)
        self.assertEqual(len(result["document_sources"]), 1)
        self.assertEqual(result["document_sources"][0]["source_type"], "news_article")
        self.assertEqual(result["document_sources"][0]["summary_text"], mock_gemini_service.return_value.invoke_json.return_value["articles"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
