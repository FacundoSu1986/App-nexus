"""Tests for src/browser/nexus_browser.py (Playwright mocked)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

from src.browser.nexus_browser import (
    NexusBrowser,
    NexusBrowserError,
    _default_chromium_user_data_dir,
    _parse_mod_id_from_url,
    _random_delay,
    NEXUS_BASE_URL,
    SKYRIM_SE_DOMAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestParseModIdFromUrl:
    def test_extracts_mod_id(self):
        assert _parse_mod_id_from_url(
            "https://www.nexusmods.com/skyrimspecialedition/mods/3328"
        ) == 3328

    def test_extracts_mod_id_with_query(self):
        assert _parse_mod_id_from_url(
            "https://www.nexusmods.com/skyrimspecialedition/mods/100?tab=files"
        ) == 100

    def test_returns_none_for_non_mod_url(self):
        assert _parse_mod_id_from_url("https://www.nexusmods.com/") is None

    def test_returns_none_for_empty_string(self):
        assert _parse_mod_id_from_url("") is None


class TestDefaultChromiumUserDataDir:
    def test_win32_uses_localappdata(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\test\\AppData\\Local")
        result = _default_chromium_user_data_dir()
        assert "Google" in result
        assert "Chrome" in result
        assert "User Data" in result

    def test_darwin_uses_library(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        result = _default_chromium_user_data_dir()
        assert "Google/Chrome" in result

    def test_linux_uses_config(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        result = _default_chromium_user_data_dir()
        assert "google-chrome" in result


class TestRandomDelay:
    def test_sleeps_in_range(self, monkeypatch):
        slept = []
        monkeypatch.setattr("src.browser.nexus_browser.time.sleep", slept.append)
        _random_delay(1.0, 2.0)
        assert len(slept) == 1
        assert 1.0 <= slept[0] <= 2.0


# ---------------------------------------------------------------------------
# NexusBrowser initialisation
# ---------------------------------------------------------------------------


class TestNexusBrowserInit:
    def test_default_game_domain(self):
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        assert browser.game_domain == SKYRIM_SE_DOMAIN

    def test_custom_user_data_dir_is_stored(self):
        browser = NexusBrowser(user_data_dir="/custom/profile")
        assert browser.user_data_dir == "/custom/profile"

    def test_headless_defaults_to_false(self):
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        assert browser.headless is False

    def test_context_is_none_before_start(self):
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        assert browser._context is None


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def _make_mock_playwright():
    """Return a MagicMock that mimics the sync_playwright() context manager."""
    mock_context = MagicMock()
    mock_chromium = MagicMock()
    mock_chromium.launch_persistent_context.return_value = mock_context
    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium
    # sync_playwright() is used as a context manager via .start()
    mock_pw_cm = MagicMock()
    mock_pw_cm.start.return_value = mock_pw
    return mock_pw_cm, mock_pw, mock_context


class TestNexusBrowserContextManager:
    def test_start_calls_launch_persistent_context(self, monkeypatch):
        mock_pw_cm, mock_pw, mock_context = _make_mock_playwright()
        monkeypatch.setattr(
            "src.browser.nexus_browser.sync_playwright",  # patched after lazy import
            lambda: mock_pw_cm,
            raising=False,
        )
        # Patch inside the module namespace that the lazy import uses
        with patch(
            "src.browser.nexus_browser.NexusBrowser._start",
            autospec=True,
        ) as mock_start:
            browser = NexusBrowser(user_data_dir="/tmp/profile")
            with browser:
                mock_start.assert_called_once()

    def test_context_none_after_stop(self):
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        # Simulate an already-started state
        browser._playwright = MagicMock()
        browser._context = MagicMock()
        browser._stop()
        assert browser._context is None
        assert browser._playwright is None

    def test_stop_is_idempotent(self):
        """Calling _stop twice should not raise."""
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        browser._stop()  # Nothing started — should be a no-op
        browser._stop()

    def test_scrape_mod_page_raises_without_start(self):
        browser = NexusBrowser(user_data_dir="/tmp/profile")
        with pytest.raises(NexusBrowserError, match="context manager"):
            browser.scrape_mod_page(3328)


# ---------------------------------------------------------------------------
# _extract_requirements
# ---------------------------------------------------------------------------


def _make_mock_page(items: list[dict] | None = None) -> MagicMock:
    """
    Build a mock Page whose query_selector_all returns a list of
    ElementHandle mocks.

    Each item dict may contain:
      - ``text``  – inner_text() return value
      - ``href``  – href attribute of the nested <a>
    """
    page = MagicMock()
    page.query_selector.return_value = None  # no tab to click

    if items is None:
        items = []

    mock_items: list[MagicMock] = []
    for spec in items:
        el = MagicMock()
        el.inner_text.return_value = spec.get("text", "")
        anchor = None
        if "href" in spec:
            anchor = MagicMock()
            anchor.get_attribute.return_value = spec["href"]
        el.query_selector.return_value = anchor
        mock_items.append(el)

    # First selector call returns items; subsequent calls return empty list.
    page.query_selector_all.side_effect = (
        lambda sel: mock_items if mock_items else []
    )
    return page


class TestExtractRequirements:
    def test_empty_page_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_mock_page([])
        result = browser._extract_requirements(page, mod_id=1)
        assert result == []

    def test_single_requirement_no_href(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_mock_page([{"text": "SKSE64"}])
        result = browser._extract_requirements(page, mod_id=1)
        assert len(result) == 1
        assert result[0]["required_name"] == "SKSE64"
        assert result[0]["required_url"] == ""
        assert result[0]["required_mod_id"] is None
        assert result[0]["is_patch"] is False

    def test_patch_detection(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_mock_page(
            [
                {"text": "Unofficial Skyrim Patch"},
                {"text": "SKSE64"},
                {"text": "Bug Fix Compilation"},
                {"text": "Compatibility Patch"},
            ]
        )
        result = browser._extract_requirements(page, mod_id=1)
        names_is_patch = {r["required_name"]: r["is_patch"] for r in result}
        assert names_is_patch["Unofficial Skyrim Patch"] is True
        assert names_is_patch["SKSE64"] is False
        assert names_is_patch["Bug Fix Compilation"] is True
        assert names_is_patch["Compatibility Patch"] is True

    def test_href_and_mod_id_extracted(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        href = "https://www.nexusmods.com/skyrimspecialedition/mods/100"
        page = _make_mock_page([{"text": "SkyUI", "href": href}])
        result = browser._extract_requirements(page, mod_id=1)
        assert result[0]["required_url"] == href
        assert result[0]["required_mod_id"] == 100

    def test_skips_empty_text_items(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_mock_page([{"text": ""}, {"text": "  "}, {"text": "SKSE64"}])
        result = browser._extract_requirements(page, mod_id=1)
        assert len(result) == 1
        assert result[0]["required_name"] == "SKSE64"


# ---------------------------------------------------------------------------
# _extract_posts
# ---------------------------------------------------------------------------


def _make_posts_page(comment_texts: list[str]) -> MagicMock:
    """Build a mock Page for the posts tab."""
    page = MagicMock()
    page.goto.return_value = None

    mock_elements = []
    for text in comment_texts:
        el = MagicMock()
        el.inner_text.return_value = text
        mock_elements.append(el)

    page.query_selector_all.side_effect = (
        lambda sel: mock_elements if mock_elements else []
    )
    return page


class TestExtractPosts:
    def test_empty_posts_returns_empty_lists(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_posts_page([])
        result = browser._extract_posts(page, base_url="https://example.com")
        assert result == {"patches": [], "known_issues": []}

    def test_patch_mention_extracted(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_posts_page(
            ["Use the compatibility patch for SkyUI", "Great mod!"]
        )
        result = browser._extract_posts(page, base_url="https://example.com")
        assert len(result["patches"]) == 1
        assert "patch" in result["patches"][0].lower()

    def test_known_issue_extracted(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = _make_posts_page(
            ["There is a bug with the inventory", "Works fine for me"]
        )
        result = browser._extract_posts(page, base_url="https://example.com")
        assert len(result["known_issues"]) == 1
        assert "bug" in result["known_issues"][0].lower()

    def test_duplicates_are_removed(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        # Same patch line mentioned twice across two comments
        page = _make_posts_page(
            [
                "Use the compatibility patch for SkyUI",
                "Use the compatibility patch for SkyUI",
            ]
        )
        result = browser._extract_posts(page, base_url="https://example.com")
        assert len(result["patches"]) == 1

    def test_goto_failure_returns_empty(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        page = MagicMock()
        page.goto.side_effect = Exception("Network error")
        result = browser._extract_posts(page, base_url="https://example.com")
        assert result == {"patches": [], "known_issues": []}

    def test_multiline_comment_extracts_relevant_lines_only(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")
        comment = "Great mod overall.\nUse the compatibility patch.\nNo issues here."
        page = _make_posts_page([comment])
        result = browser._extract_posts(page, base_url="https://example.com")
        assert len(result["patches"]) == 1
        assert result["patches"][0] == "Use the compatibility patch."


# ---------------------------------------------------------------------------
# scrape_mod_page integration (mocked browser context)
# ---------------------------------------------------------------------------


class TestScrapeModPage:
    def _make_browser_with_mock_context(self, monkeypatch):
        """Return a NexusBrowser whose _context is a MagicMock."""
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")

        mock_page = MagicMock()
        mock_page.goto.return_value = None
        mock_page.query_selector.return_value = None
        mock_page.query_selector_all.return_value = []

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        browser._context = mock_context

        return browser, mock_page

    def test_returns_expected_keys(self, monkeypatch):
        browser, _ = self._make_browser_with_mock_context(monkeypatch)
        result = browser.scrape_mod_page(3328)
        assert set(result.keys()) == {"mod_id", "requirements", "patches", "known_issues"}

    def test_mod_id_is_preserved(self, monkeypatch):
        browser, _ = self._make_browser_with_mock_context(monkeypatch)
        result = browser.scrape_mod_page(3328)
        assert result["mod_id"] == 3328

    def test_page_is_closed_after_scrape(self, monkeypatch):
        browser, mock_page = self._make_browser_with_mock_context(monkeypatch)
        browser.scrape_mod_page(3328)
        mock_page.close.assert_called_once()

    def test_page_is_closed_even_on_error(self, monkeypatch):
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")

        mock_page = MagicMock()
        mock_page.goto.side_effect = Exception("nav failed")

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        browser._context = mock_context

        with pytest.raises(Exception, match="nav failed"):
            browser.scrape_mod_page(3328)

        mock_page.close.assert_called_once()

    def test_navigates_to_correct_url(self, monkeypatch):
        browser, mock_page = self._make_browser_with_mock_context(monkeypatch)
        browser.scrape_mod_page(3328)
        expected_url = (
            f"{NEXUS_BASE_URL}/{SKYRIM_SE_DOMAIN}/mods/3328"
        )
        mock_page.goto.assert_any_call(
            expected_url, wait_until="domcontentloaded", timeout=30_000
        )

    def test_requirements_output_compatible_with_db_upsert(self, monkeypatch):
        """Returned requirement dicts must have the keys expected by upsert_requirements."""
        monkeypatch.setattr("src.browser.nexus_browser._random_delay", lambda *_: None)
        browser = NexusBrowser(user_data_dir="/tmp/p")

        mock_page = MagicMock()
        mock_page.goto.return_value = None
        mock_page.query_selector.return_value = None

        # Simulate one requirement item
        el = MagicMock()
        el.inner_text.return_value = "SKSE64"
        anchor = MagicMock()
        anchor.get_attribute.return_value = (
            "https://www.nexusmods.com/skyrimspecialedition/mods/3328"
        )
        el.query_selector.return_value = anchor
        mock_page.query_selector_all.return_value = [el]

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page
        browser._context = mock_context

        result = browser.scrape_mod_page(9999)
        for req in result["requirements"]:
            assert "required_name" in req
            assert "required_url" in req
            assert "required_mod_id" in req
            assert "is_patch" in req
