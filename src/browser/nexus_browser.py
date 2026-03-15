"""
Playwright-based browser agent for Nexus Mods page analysis.

WARNING: This module is designed for analyzing ONE mod at a time at human-like
speed using the user's own authenticated browser session. It is NOT intended
for mass scraping or automated bulk operations.

Uses slow_mo=random(2000,4000) to simulate human browsing speed (2-4 seconds
between actions).
"""

import logging
import random
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Global concurrency lock — only one analysis can run at a time
_analysis_lock = threading.Lock()


def _random_delay() -> int:
    """Return a random slow_mo delay between 2000 and 4000 ms (human-like speed)."""
    return random.randint(2000, 4000)


class NexusBrowser:
    """
    Playwright browser agent that navigates Nexus Mods pages using the user's
    existing authenticated Chromium session.

    Design constraints:
    - ONE mod at a time only (enforced by _analysis_lock).
    - Human-like speed: slow_mo is randomised between 2000-4000 ms per action.
    - Uses a persistent browser context so the user's Nexus login is preserved.
    """

    # Nexus Mods URL pattern for Skyrim SE mods
    MOD_URL_TEMPLATE = "https://www.nexusmods.com/skyrimspecialedition/mods/{nexus_id}"

    def __init__(self, user_data_dir: Optional[str] = None):
        """
        Parameters
        ----------
        user_data_dir:
            Path to a Chromium user data directory containing an existing
            authenticated Nexus Mods session.  When None the default Chromium
            profile location is used.
        """
        self.user_data_dir = user_data_dir or _default_chromium_profile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_mod_page(self, nexus_id: str) -> dict:
        """
        Navigate to a single mod page and extract analysis content.

        This method acquires a global lock so only one mod is ever being
        analysed at a time.

        Parameters
        ----------
        nexus_id:
            The numeric Nexus Mods ID of the mod to analyse.

        Returns
        -------
        dict with keys:
            - nexus_id (str)
            - url (str)
            - requirements_html (str)  — raw HTML of the requirements section
            - comments_html (str)      — raw HTML of the posts/comments section
            - requirements_text (str)  — plain text of the requirements section
            - comments_text (str)      — plain text of the posts/comments section
        """
        if not _analysis_lock.acquire(blocking=False):
            raise RuntimeError(
                "Another mod analysis is already running. "
                "Only one analysis is allowed at a time."
            )
        try:
            return self._do_fetch(nexus_id)
        finally:
            _analysis_lock.release()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_fetch(self, nexus_id: str) -> dict:
        """
        Internal: run Playwright, navigate, extract content.
        Runs inside the concurrency lock.
        """
        # Import here so that apps without Playwright installed can still
        # import this module (the error surfaces only when fetch_mod_page is called)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright>=1.40.0 "
                "and then: playwright install chromium"
            ) from exc

        url = self.MOD_URL_TEMPLATE.format(nexus_id=nexus_id)
        slow_mo = _random_delay()
        logger.info(
            "Launching Playwright (slow_mo=%d ms) for mod %s", slow_mo, nexus_id
        )

        with sync_playwright() as pw:
            # Use a persistent context so the user's authenticated session is reused
            context = pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False,  # visible browser so the user can see what is happening
                slow_mo=slow_mo,
                args=["--no-sandbox"],
            )
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded")
                logger.info("Navigated to %s", url)

                requirements_html, requirements_text = self._extract_requirements(page)
                comments_html, comments_text = self._extract_comments(page)
            finally:
                context.close()

        return {
            "nexus_id": str(nexus_id),
            "url": url,
            "requirements_html": requirements_html,
            "requirements_text": requirements_text,
            "comments_html": comments_html,
            "comments_text": comments_text,
        }

    # ------------------------------------------------------------------
    # Page extraction helpers (testable without live browser)
    # ------------------------------------------------------------------

    @staticmethod
    def extract_requirements_from_html(html: str) -> str:
        """
        Parse requirements section text from raw HTML.

        Accepts either a full page HTML string or just the requirements
        section fragment.  Returns normalised plain text.
        """
        return _extract_text_from_html(html)

    @staticmethod
    def extract_comments_from_html(html: str) -> str:
        """
        Parse comments/posts section text from raw HTML.

        Returns normalised plain text.
        """
        return _extract_text_from_html(html)

    def _extract_requirements(self, page) -> tuple[str, str]:
        """Extract the requirements dropdown section from a live Playwright page."""
        try:
            # The requirements section on Nexus mod pages uses a 'tab' with id
            # or aria-label containing 'requirements'. Try a few selectors.
            selectors = [
                "[data-target='#requirements']",
                "#requirements",
                "div.requirements",
                "div[class*='requirement']",
                "section[id*='requirement']",
            ]
            html = ""
            for sel in selectors:
                try:
                    elem = page.query_selector(sel)
                    if elem:
                        html = elem.inner_html()
                        break
                except Exception:
                    continue

            if not html:
                # Fall back: grab the full page HTML and let the AI parse it
                html = page.content()
                logger.warning(
                    "Requirements selector not found; using full page HTML."
                )

            text = _extract_text_from_html(html)
            return html, text
        except Exception as exc:
            logger.error("Error extracting requirements: %s", exc)
            return "", ""

    def _extract_comments(self, page) -> tuple[str, str]:
        """Extract the posts/comments section from a live Playwright page."""
        try:
            selectors = [
                "section.comments",
                "div#comments",
                "div[class*='comment']",
                "div[id*='comment']",
            ]
            html = ""
            for sel in selectors:
                try:
                    elem = page.query_selector(sel)
                    if elem:
                        html = elem.inner_html()
                        break
                except Exception:
                    continue

            if not html:
                html = ""
                logger.warning("Comments selector not found; comments not extracted.")

            text = _extract_text_from_html(html)
            return html, text
        except Exception as exc:
            logger.error("Error extracting comments: %s", exc)
            return "", ""


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _extract_text_from_html(html: str) -> str:
    """
    Strip HTML tags from a string and return normalised plain text.

    Uses the standard-library ``html.parser`` — no external dependencies.
    """
    if not html:
        return ""

    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: list[str] = []

        def handle_data(self, data: str) -> None:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

        def get_text(self) -> str:
            return "\n".join(self._parts)

    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.get_text()


def _default_chromium_profile() -> str:
    """Return the default Chromium user-data-dir for the current OS."""
    import os
    import sys

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(local_app_data, "Google", "Chrome", "User Data")
    if sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Google/Chrome"
        )
    # Linux
    return os.path.expanduser("~/.config/google-chrome")
