"""
Unit tests for the NexusBrowser helper functions (src/browser/nexus_browser.py).

Tests cover the extraction/parsing helpers that work without a live browser
session (using saved HTML fragments as fixtures).
"""

import pytest

from src.browser.nexus_browser import (
    NexusBrowser,
    _extract_text_from_html,
    _default_chromium_profile,
)


class TestExtractTextFromHtml:
    def test_plain_text_unchanged(self):
        text = _extract_text_from_html("Hello world")
        assert "Hello" in text
        assert "world" in text

    def test_strips_html_tags(self):
        html = "<p>Requires <b>SKSE64</b> and <a href='#'>SkyUI</a></p>"
        text = _extract_text_from_html(html)
        assert "Requires" in text
        assert "SKSE64" in text
        assert "SkyUI" in text
        assert "<" not in text
        assert ">" not in text

    def test_empty_html_returns_empty_string(self):
        assert _extract_text_from_html("") == ""

    def test_ignores_empty_tags(self):
        html = "<div><span></span></div>"
        result = _extract_text_from_html(html)
        assert result == ""

    def test_multiline_html(self):
        html = (
            "<ul>\n"
            "  <li>SKSE64</li>\n"
            "  <li>SkyUI</li>\n"
            "  <li>Patch for ModX</li>\n"
            "</ul>"
        )
        text = _extract_text_from_html(html)
        assert "SKSE64" in text
        assert "SkyUI" in text
        assert "Patch for ModX" in text

    def test_html_entities_decoded(self):
        html = "<p>Version &gt;= 1.0 &amp; SkyUI</p>"
        text = _extract_text_from_html(html)
        assert "Version" in text
        assert "SkyUI" in text


class TestNexusBrowserStaticHelpers:
    def test_extract_requirements_from_html(self):
        html = (
            "<div class='requirements'>"
            "<ul><li>SKSE64</li><li>SkyUI</li></ul>"
            "</div>"
        )
        text = NexusBrowser.extract_requirements_from_html(html)
        assert "SKSE64" in text
        assert "SkyUI" in text

    def test_extract_comments_from_html(self):
        html = (
            "<div class='comments'>"
            "<p>Known issue: crashes when both ModA and ModB are loaded.</p>"
            "</div>"
        )
        text = NexusBrowser.extract_comments_from_html(html)
        assert "crashes" in text
        assert "ModA" in text


class TestDefaultChromiumProfile:
    def test_returns_non_empty_string(self):
        path = _default_chromium_profile()
        assert isinstance(path, str)
        assert len(path) > 0

    def test_platform_specific_path(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        path = _default_chromium_profile()
        assert "google-chrome" in path or "chromium" in path.lower() or "chrome" in path.lower()

    def test_windows_path(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")
        path = _default_chromium_profile()
        assert "Chrome" in path or "chrome" in path.lower()

    def test_macos_path(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        path = _default_chromium_profile()
        assert "Chrome" in path


class TestConcurrencyLock:
    def test_lock_released_after_failed_import(self):
        """
        Confirm the concurrency lock is released even when the internal
        _do_fetch raises an ImportError (Playwright not installed).
        """
        from src.browser import nexus_browser as nb

        browser = NexusBrowser()

        # Monkeypatch so that the import inside _do_fetch raises ImportError
        original_do_fetch = browser._do_fetch

        def failing_do_fetch(nexus_id):
            raise ImportError("simulated missing playwright")

        browser._do_fetch = failing_do_fetch

        with pytest.raises(ImportError):
            browser.fetch_mod_page("12345")

        # Lock must now be acquirable (i.e. released by finally block)
        acquired = nb._analysis_lock.acquire(blocking=False)
        assert acquired, "Lock was not released after an exception in fetch_mod_page"
        nb._analysis_lock.release()
