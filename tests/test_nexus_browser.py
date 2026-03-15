"""Tests for the Playwright browser agent."""

import pytest
from unittest.mock import patch, MagicMock

from src.browser.nexus_browser import (
    _human_delay,
    MOD_PAGE_URL,
    extract_mod_page_data,
)


class TestHumanDelay:
    def test_returns_int_between_2000_and_4000(self):
        for _ in range(50):
            delay = _human_delay()
            assert 2000 <= delay <= 4000


class TestModPageUrl:
    def test_url_format(self):
        url = MOD_PAGE_URL.format(nexus_id="2347")
        assert url == "https://www.nexusmods.com/skyrimspecialedition/mods/2347"


class TestExtractModPageData:
    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_expected_keys(self, mock_import):
        """Verify the function returns the correct dict structure."""
        # Build the mock chain: sync_playwright -> pw -> browser -> context -> page
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        # sync_playwright() returns a context manager yielding mock_pw
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_pw)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_import.return_value = lambda: mock_cm

        result = extract_mod_page_data("12345", headless=True)

        assert "requirements_html" in result
        assert "posts_html" in result
        assert "description_html" in result

    @patch("src.browser.nexus_browser._import_playwright")
    def test_extracts_html_from_selectors(self, mock_import):
        """When selectors match, the HTML content is captured."""
        mock_element = MagicMock()
        mock_element.inner_html.return_value = "<p>SKSE64 required</p>"

        mock_page = MagicMock()
        mock_page.query_selector.return_value = mock_element

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_pw)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_import.return_value = lambda: mock_cm

        result = extract_mod_page_data("12345", headless=True)

        assert result["requirements_html"] == "<p>SKSE64 required</p>"
        assert result["description_html"] == "<p>SKSE64 required</p>"
        assert result["posts_html"] == "<p>SKSE64 required</p>"

    def test_import_error_when_playwright_missing(self):
        """When playwright is not installed, a clear ImportError is raised."""
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            from src.browser import nexus_browser
            # Reset the cached import
            nexus_browser._sync_playwright = None
            with pytest.raises(ImportError, match="Playwright is not installed"):
                nexus_browser._import_playwright()
