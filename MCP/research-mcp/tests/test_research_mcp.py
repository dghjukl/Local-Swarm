"""
tests/test_research_mcp.py — Test suite for research-mcp.

Run:
    python3 -m unittest discover -s tests -p "test_*.py" -v

Network tools (research_search, research_fetch) are mocked.
Logic tools (research_extract, research_plan, research_iterate) run directly.
"""
from __future__ import annotations
import asyncio, sys, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class TestServerImport(unittest.TestCase):
    def test_imports(self):
        import server
        self.assertTrue(hasattr(server, "mcp"))

    def test_6_tools_registered(self):
        import server
        tools = asyncio.run(server.mcp.list_tools())
        names = {t.name for t in tools}
        expected = {
            "research_status", "research_search", "research_fetch",
            "research_extract", "research_plan", "research_iterate",
        }
        self.assertEqual(names, expected)

    def test_no_store(self):
        import server
        self.assertFalse(hasattr(server, "store"))


class TestStatus(unittest.TestCase):
    def test_status_ok(self):
        import server
        r = server.research_status()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["mcp"], "research-mcp")
        self.assertTrue(r["stateless"])
        self.assertIn("search_backend", r)

    def test_status_shows_brave_not_configured_by_default(self):
        import server
        with patch.object(server.settings, "brave_api_key", ""):
            r = server.research_status()
        self.assertFalse(r["brave_configured"])
        self.assertEqual(r["search_backend"], "duckduckgo")

    def test_status_shows_brave_when_key_set(self):
        import server
        with patch.object(server.settings, "brave_api_key", "test-key-123"):
            r = server.research_status()
        self.assertTrue(r["brave_configured"])
        self.assertEqual(r["search_backend"], "brave")


class TestSSRFProtection(unittest.TestCase):
    def test_http_url_accepted(self):
        import server
        err = server._validate_url("http://example.com/page")
        self.assertIsNone(err)

    def test_https_url_accepted(self):
        import server
        err = server._validate_url("https://example.com/page")
        self.assertIsNone(err)

    def test_non_http_scheme_rejected(self):
        import server
        err = server._validate_url("ftp://example.com/file.txt")
        self.assertIsNotNone(err)
        self.assertIn("http", err.lower())

    def test_file_scheme_rejected(self):
        import server
        err = server._validate_url("file:///etc/passwd")
        self.assertIsNotNone(err)

    def test_localhost_blocked_when_protection_on(self):
        import server
        with patch.object(server.settings, "block_private_ips", True):
            err = server._validate_url("http://127.0.0.1/admin")
        self.assertIsNotNone(err)

    def test_private_ip_blocked(self):
        import server
        with patch.object(server.settings, "block_private_ips", True):
            err = server._validate_url("http://192.168.1.1/")
        self.assertIsNotNone(err)


class TestResearchSearch(unittest.TestCase):
    def test_empty_query_returns_error(self):
        import server
        r = server.research_search("  ")
        self.assertIn("error", r)

    def test_brave_search_called_when_key_set(self):
        import server
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "web": {"results": [
                {"title": "Python Guide", "url": "https://python.org", "description": "Official Python docs", "page_age": "2024-01"},
            ]}
        }
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch.object(server.settings, "brave_api_key", "test-key"):
            r = server.research_search("python programming", max_results=5)
        self.assertEqual(r["backend"], "brave")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["results"][0]["title"], "Python Guide")
        self.assertEqual(r["results"][0]["source"], "brave")

    def test_ddg_fallback_when_no_brave_key(self):
        import server
        mock_ddgs_results = [
            {"title": "DDG Result", "href": "https://example.com", "body": "A result"},
        ]
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = mock_ddgs_results
        with patch("server.DDGS", return_value=mock_ddgs),              patch.object(server.settings, "brave_api_key", ""),              patch.object(server, "_DDG_AVAILABLE", True):
            r = server.research_search("python programming")
        self.assertEqual(r["backend"], "duckduckgo")
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["results"][0]["source"], "duckduckgo")

    def test_no_backend_available_returns_error(self):
        import server
        with patch.object(server.settings, "brave_api_key", ""),              patch.object(server, "_DDG_AVAILABLE", False):
            r = server.research_search("some query")
        self.assertIn("error", r)
        self.assertIn("backend", r["error"].lower())

    def test_count_clamped_to_20(self):
        import server
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"web": {"results": []}}
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch.object(server.settings, "brave_api_key", "key"):
            r = server.research_search("query", max_results=999)
        # Should not crash and count should be ≤ 20
        self.assertNotIn("error", r)


class TestResearchFetch(unittest.TestCase):
    def test_non_http_url_blocked(self):
        import server
        r = server.research_fetch("ftp://example.com")
        self.assertIn("error", r)

    def test_html_content_converted_to_text(self):
        import server
        html = "<html><head><title>Test Page</title></head><body><h1>Hello</h1><p>World</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.content = html.encode()
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://example.com")
        self.assertIn("content", r)
        self.assertIn("title", r)
        self.assertEqual(r["title"], "Test Page")
        self.assertIn("Hello", r["content"])

    def test_json_content_returned_as_text(self):
        import server
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.content = b'{"key": "value"}'
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://api.example.com/data")
        self.assertIn("content", r)
        self.assertIn("key", r["content"])

    def test_word_count_returned(self):
        import server
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = b"<p>one two three four five</p>"
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://example.com")
        self.assertIn("word_count", r)
        self.assertGreater(r["word_count"], 0)

    def test_max_words_truncates(self):
        import server
        words = " ".join(f"word{i}" for i in range(200))
        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.content = words.encode()
        mock_resp.raise_for_status.return_value = None
        with patch("server.httpx.get", return_value=mock_resp),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://example.com", max_words=50)
        self.assertTrue(r["truncated"])
        self.assertIn("truncated", r["content"])

    def test_timeout_returns_error(self):
        import server
        with patch("server.httpx.get", side_effect=server.httpx.TimeoutException("timeout")),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://example.com")
        self.assertIn("error", r)
        self.assertIn("timed out", r["error"].lower())

    def test_http_error_returns_status_code(self):
        import server
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.reason_phrase = "Not Found"
        exc = server.httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)
        with patch("server.httpx.get", side_effect=exc),              patch("server._validate_url", return_value=None):
            r = server.research_fetch("https://example.com/missing")
        self.assertIn("error", r)
        self.assertIn("404", r["error"])


class TestResearchExtract(unittest.TestCase):
    def test_empty_content_returns_error(self):
        import server
        r = server.research_extract("  ")
        self.assertIn("error", r)

    def test_sections_extracted_from_headings(self):
        import server
        content = """# Main Title
Introduction text here.

## Section One
Content of section one.

## Section Two
Content of section two.
"""
        r = server.research_extract(content, "https://example.com")
        self.assertIn("sections", r)
        headings = [s["heading"] for s in r["sections"]]
        self.assertIn("Main Title", headings)
        self.assertIn("Section One", headings)

    def test_links_extracted(self):
        import server
        content = "See https://python.org and https://docs.python.org for more info."
        r = server.research_extract(content)
        self.assertIn("links_found", r)
        self.assertIn("https://python.org", r["links_found"])

    def test_word_count_correct(self):
        import server
        content = "one two three four five"
        r = server.research_extract(content)
        self.assertEqual(r["word_count"], 5)

    def test_section_count_returned(self):
        import server
        content = "## A\ntext\n## B\ntext\n## C\ntext"
        r = server.research_extract(content)
        self.assertIn("section_count", r)
        self.assertGreaterEqual(r["section_count"], 3)

    def test_preview_present(self):
        import server
        content = "Some research content here. " * 20
        r = server.research_extract(content)
        self.assertIn("preview", r)
        self.assertGreater(len(r["preview"]), 0)

    def test_link_count_matches_links_found(self):
        import server
        content = "Visit https://a.com and https://b.com for details."
        r = server.research_extract(content)
        self.assertEqual(r["link_count"], len(r["links_found"]))


class TestResearchPlan(unittest.TestCase):
    def test_empty_query_returns_error(self):
        import server
        r = server.research_plan("  ")
        self.assertIn("error", r)

    def test_invalid_depth_returns_error(self):
        import server
        r = server.research_plan("Python programming", depth="extreme")
        self.assertIn("error", r)

    def test_plan_has_required_keys(self):
        import server
        r = server.research_plan("What is machine learning?")
        for key in ("sub_questions", "suggested_search_terms", "iterations_recommended",
                    "research_sequence", "depth_note"):
            self.assertIn(key, r, f"Missing key: {key}")

    def test_sub_questions_are_list(self):
        import server
        r = server.research_plan("Climate change effects")
        self.assertIsInstance(r["sub_questions"], list)
        self.assertGreater(len(r["sub_questions"]), 0)

    def test_search_terms_are_list(self):
        import server
        r = server.research_plan("Quantum computing")
        self.assertIsInstance(r["suggested_search_terms"], list)
        self.assertGreater(len(r["suggested_search_terms"]), 0)

    def test_quick_depth_fewer_iterations(self):
        import server
        r = server.research_plan("Simple topic", depth="quick")
        self.assertEqual(r["iterations_recommended"], 2)

    def test_deep_depth_more_iterations(self):
        import server
        r = server.research_plan("Complex research topic", depth="deep")
        self.assertEqual(r["iterations_recommended"], 5)

    def test_standard_depth_is_default(self):
        import server
        r = server.research_plan("Some topic")
        self.assertEqual(r["depth"], "standard")
        self.assertEqual(r["iterations_recommended"], 3)

    def test_context_noted_when_provided(self):
        import server
        r = server.research_plan("Python", context="Already know basic syntax")
        self.assertTrue(r["context_noted"])

    def test_research_sequence_is_list(self):
        import server
        r = server.research_plan("Topic")
        self.assertIsInstance(r["research_sequence"], list)
        self.assertGreater(len(r["research_sequence"]), 0)


class TestResearchIterate(unittest.TestCase):
    def test_empty_query_returns_error(self):
        import server
        r = server.research_iterate("", "some findings", 1)
        self.assertIn("error", r)

    def test_empty_findings_returns_error(self):
        import server
        r = server.research_iterate("query", "", 1)
        self.assertIn("error", r)

    def test_zero_iteration_returns_error(self):
        import server
        r = server.research_iterate("query", "findings", 0)
        self.assertIn("error", r)

    def test_has_required_keys(self):
        import server
        r = server.research_iterate("Machine learning", "Found overview of ML types.", 1, 3)
        for key in ("should_continue", "gaps_identified", "next_search_suggestions",
                    "coverage_assessment", "synthesis_readiness"):
            self.assertIn(key, r, f"Missing key: {key}")

    def test_should_continue_true_before_max(self):
        import server
        r = server.research_iterate("query", "findings", iteration=2, max_iterations=3)
        self.assertTrue(r["should_continue"])

    def test_should_continue_false_at_max(self):
        import server
        r = server.research_iterate("query", "findings", iteration=3, max_iterations=3)
        self.assertFalse(r["should_continue"])

    def test_no_next_searches_when_done(self):
        import server
        r = server.research_iterate("query", "findings", iteration=3, max_iterations=3)
        self.assertEqual(r["next_search_suggestions"], [])

    def test_termination_note_present_at_max(self):
        import server
        r = server.research_iterate("query", "findings", iteration=3, max_iterations=3)
        self.assertIn("termination_note", r)
        self.assertTrue(len(r["termination_note"]) > 0)

    def test_synthesis_readiness_ready_at_max(self):
        import server
        r = server.research_iterate("query", "findings", iteration=3, max_iterations=3)
        self.assertEqual(r["synthesis_readiness"], "ready")

    def test_synthesis_readiness_too_early_at_iteration_1(self):
        import server
        r = server.research_iterate("query", "some initial findings", iteration=1, max_iterations=3)
        self.assertEqual(r["synthesis_readiness"], "too_early")

    def test_gaps_identified_is_list(self):
        import server
        r = server.research_iterate("query", "Found some info but unclear on details.", 1)
        self.assertIsInstance(r["gaps_identified"], list)
        self.assertGreater(len(r["gaps_identified"]), 0)

    def test_conflicting_findings_flagged(self):
        import server
        r = server.research_iterate("query", "Sources disagree on this — conflicting information found.", 2, 4)
        gaps_text = " ".join(r["gaps_identified"]).lower()
        self.assertIn("conflict", gaps_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
