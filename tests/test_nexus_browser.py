"""Tests for the Playwright browser agent."""

import logging
import os

import pytest
from unittest.mock import patch, MagicMock, call

from src.browser.nexus_browser import (
    _human_delay,
    MOD_PAGE_URL,
    DOWNLOAD_PAGE_URL,
    extract_mod_page_data,
    download_mod_file,
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

    @patch("src.browser.nexus_browser._import_playwright")
    def test_clicks_requirements_tab(self, mock_import):
        """Verify the function clicks the Requirements tab when found."""
        mock_req_tab = MagicMock()
        mock_element = MagicMock()
        mock_element.inner_html.return_value = "<p>SKSE64</p>"

        mock_page = MagicMock()
        # First query_selector call finds the requirements tab,
        # second finds the requirements section, etc.
        mock_page.query_selector.side_effect = [
            mock_req_tab,   # req tab
            mock_element,   # req section
            mock_element,   # desc section
            MagicMock(),    # posts tab
            mock_element,   # posts section
        ]

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

        extract_mod_page_data("12345", headless=True)

        mock_req_tab.click.assert_called_once()

    @patch("src.browser.nexus_browser._import_playwright")
    def test_debug_logging_on_successful_extraction(self, mock_import, caplog):
        """Verify debug logs are emitted when HTML is successfully extracted."""
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

        with caplog.at_level(logging.DEBUG, logger="src.browser.nexus_browser"):
            extract_mod_page_data("12345", headless=True)

        assert any("Requirements HTML extracted" in m for m in caplog.messages)
        assert any("Posts HTML extracted" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_debug_logging_on_empty_selectors(self, mock_import, caplog):
        """Verify debug logs are emitted when selectors match nothing."""
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None

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

        with caplog.at_level(logging.DEBUG, logger="src.browser.nexus_browser"):
            extract_mod_page_data("12345", headless=True)

        assert any("selector matched nothing" in m for m in caplog.messages)


class TestDownloadPageUrl:
    def test_url_format(self):
        url = DOWNLOAD_PAGE_URL.format(nexus_id="2347", file_id="9999")
        assert url == (
            "https://www.nexusmods.com/skyrimspecialedition/mods/2347"
            "?tab=files&file_id=9999"
        )


class TestDownloadModFile:
    def _build_mocks(self, *, slow_btn=None, download_obj=None,
                     wait_for_selector_side_effect=None):
        """Return (mock_import, mock_page, mock_context) with common wiring."""
        mock_page = MagicMock()

        # Support both returning a value and raising on wait_for_selector
        if wait_for_selector_side_effect is not None:
            mock_page.wait_for_selector.side_effect = wait_for_selector_side_effect
        else:
            mock_page.wait_for_selector.return_value = slow_btn

        if download_obj is not None:
            download_cm = MagicMock()
            download_cm.__enter__ = MagicMock(return_value=download_cm)
            download_cm.__exit__ = MagicMock(return_value=False)
            download_cm.value = download_obj
            mock_page.expect_download.return_value = download_cm

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_pw)
        mock_cm.__exit__ = MagicMock(return_value=False)

        mock_import = MagicMock(return_value=lambda: mock_cm)
        return mock_import, mock_page, mock_context

    @patch("src.browser.nexus_browser._import_playwright")
    def test_successful_download(self, mock_import_patch, tmp_path):
        """Happy path: file is downloaded and path returned."""
        mock_download = MagicMock()
        mock_download.suggested_filename = "MyMod-1.0.zip"

        mock_slow_btn = MagicMock()
        mock_import, mock_page, _ = self._build_mocks(
            slow_btn=mock_slow_btn, download_obj=mock_download,
        )
        mock_import_patch.return_value = mock_import.return_value

        out = str(tmp_path / "downloads")
        result = download_mod_file("2347", "9999", out, headless=True)

        assert result is not None
        assert result.endswith("MyMod-1.0.zip")
        mock_slow_btn.click.assert_called_once()
        mock_download.save_as.assert_called_once()

    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_none_when_button_missing(self, mock_import_patch, tmp_path):
        """When the Slow Download button is not found (TimeoutError), return None."""
        mock_import, _, _ = self._build_mocks(
            wait_for_selector_side_effect=TimeoutError("Timeout"),
        )
        mock_import_patch.return_value = mock_import.return_value

        out = str(tmp_path / "downloads")
        result = download_mod_file("2347", "9999", out, headless=True)

        assert result is None

    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_none_on_download_failure(self, mock_import_patch, tmp_path):
        """When expect_download raises, return None gracefully."""
        mock_slow_btn = MagicMock()
        mock_import, mock_page, _ = self._build_mocks(slow_btn=mock_slow_btn)
        mock_import_patch.return_value = mock_import.return_value
        # Make expect_download raise an error
        mock_page.expect_download.side_effect = Exception("timeout")

        out = str(tmp_path / "downloads")
        result = download_mod_file("2347", "9999", out, headless=True)

        assert result is None

    @patch("src.browser.nexus_browser._import_playwright")
    def test_creates_output_directory(self, mock_import_patch, tmp_path):
        """Output directory is created if it doesn't exist."""
        mock_import, _, _ = self._build_mocks(
            wait_for_selector_side_effect=TimeoutError("Timeout"),
        )
        mock_import_patch.return_value = mock_import.return_value

        nested = str(tmp_path / "a" / "b" / "c")
        download_mod_file("2347", "9999", nested, headless=True)

        assert os.path.isdir(nested)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_uses_persistent_context_with_user_data_dir(self, mock_import_patch, tmp_path):
        """When user_data_dir is provided, launch_persistent_context is used."""
        mock_import, _, _ = self._build_mocks(
            wait_for_selector_side_effect=TimeoutError("Timeout"),
        )
        mock_import_patch.return_value = mock_import.return_value

        # Access the mock_pw from inside the lambda/context-manager
        mock_cm_fn = mock_import_patch.return_value
        mock_cm_obj = mock_cm_fn()
        mock_pw = mock_cm_obj.__enter__()

        out = str(tmp_path / "downloads")
        download_mod_file("2347", "9999", out, user_data_dir="/fake/profile", headless=True)

        mock_pw.chromium.launch_persistent_context.assert_called_once()

    @patch("src.browser.nexus_browser._import_playwright")
    def test_logs_countdown_message(self, mock_import_patch, tmp_path, caplog):
        """Verify the countdown log message is emitted."""
        mock_download = MagicMock()
        mock_download.suggested_filename = "mod.zip"

        mock_slow_btn = MagicMock()
        mock_import, _, _ = self._build_mocks(
            slow_btn=mock_slow_btn, download_obj=mock_download,
        )
        mock_import_patch.return_value = mock_import.return_value

        out = str(tmp_path / "downloads")
        with caplog.at_level(logging.INFO, logger="src.browser.nexus_browser"):
            download_mod_file("2347", "9999", out, headless=True)

        assert any("5-second countdown" in m for m in caplog.messages)
        assert any("Clicking Slow Download" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_logs_warning_when_button_missing(self, mock_import_patch, tmp_path, caplog):
        """Verify a warning is logged when the Slow Download button times out."""
        mock_import, _, _ = self._build_mocks(
            wait_for_selector_side_effect=TimeoutError("Timeout"),
        )
        mock_import_patch.return_value = mock_import.return_value

        out = str(tmp_path / "downloads")
        with caplog.at_level(logging.WARNING, logger="src.browser.nexus_browser"):
            download_mod_file("2347", "9999", out, headless=True)

        assert any("Slow Download button not found" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_none_on_network_error(self, mock_import_patch, tmp_path, caplog):
        """When a network error occurs during download, return None and log."""
        mock_slow_btn = MagicMock()
        mock_import, mock_page, _ = self._build_mocks(slow_btn=mock_slow_btn)
        mock_import_patch.return_value = mock_import.return_value
        # Simulate a network disconnection during expect_download
        mock_page.expect_download.side_effect = ConnectionError("Connection lost")

        out = str(tmp_path / "downloads")
        with caplog.at_level(logging.WARNING, logger="src.browser.nexus_browser"):
            result = download_mod_file("2347", "9999", out, headless=True)

        assert result is None
        assert any("Network error" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_none_on_download_timeout(self, mock_import_patch, tmp_path, caplog):
        """When the download itself times out (e.g. countdown stalls), return None."""
        mock_slow_btn = MagicMock()
        mock_import, mock_page, _ = self._build_mocks(slow_btn=mock_slow_btn)
        mock_import_patch.return_value = mock_import.return_value

        # Build a context manager whose __exit__ raises TimeoutError,
        # simulating a Playwright download timeout after the click.
        download_cm = MagicMock()
        download_cm.__enter__ = MagicMock(return_value=download_cm)
        download_cm.__exit__ = MagicMock(side_effect=TimeoutError("Download timeout"))
        mock_page.expect_download.return_value = download_cm

        out = str(tmp_path / "downloads")
        with caplog.at_level(logging.WARNING, logger="src.browser.nexus_browser"):
            result = download_mod_file("2347", "9999", out, headless=True)

        assert result is None
        assert any("Download timed out" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_returns_none_on_navigation_error(self, mock_import_patch, tmp_path, caplog):
        """When page navigation fails due to a network error, return None."""
        mock_import, mock_page, _ = self._build_mocks()
        mock_import_patch.return_value = mock_import.return_value
        mock_page.goto.side_effect = ConnectionError("Connection refused")

        out = str(tmp_path / "downloads")
        with caplog.at_level(logging.WARNING, logger="src.browser.nexus_browser"):
            result = download_mod_file("2347", "9999", out, headless=True)

        assert result is None
        assert any("Network error navigating" in m for m in caplog.messages)

    @patch("src.browser.nexus_browser._import_playwright")
    def test_save_as_receives_correct_path(self, mock_import_patch, tmp_path):
        """Verify save_as is called with output_dir / suggested_filename."""
        mock_download = MagicMock()
        mock_download.suggested_filename = "SkyUI-5.2.zip"

        mock_slow_btn = MagicMock()
        mock_import, _, _ = self._build_mocks(
            slow_btn=mock_slow_btn, download_obj=mock_download,
        )
        mock_import_patch.return_value = mock_import.return_value

        out = str(tmp_path / "downloads")
        result = download_mod_file("2347", "9999", out, headless=True)

        expected = os.path.join(out, "SkyUI-5.2.zip")
        mock_download.save_as.assert_called_once_with(expected)
        assert result == os.path.abspath(expected)
