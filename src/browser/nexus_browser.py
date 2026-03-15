"""
Playwright-based browser agent for Nexus Mods page analysis.

Uses the user's existing Chromium browser profile (persistent context) to
browse mod pages as an authenticated user.  Navigation is intentionally slow
(2–4 seconds between actions) to mimic human behaviour and avoid triggering
anti-bot measures.

This is NOT mass scraping — it analyses one mod at a time, at human speed,
using the user's own account.
"""

from __future__ import annotations

import logging
import os
import random
import re
import sys
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, ElementHandle, Page

logger = logging.getLogger(__name__)

NEXUS_BASE_URL = "https://www.nexusmods.com"
SKYRIM_SE_DOMAIN = "skyrimspecialedition"

# Regex to detect patch / fix / compatibility references in text.
_PATCH_RE = re.compile(r"\bpatch\b|\bfix\b|\bcompat\w*\b", re.IGNORECASE)

# Regex to detect known-issue / bug / conflict mentions in text.
_ISSUE_RE = re.compile(
    r"\bbug\b|\berror\b|\bcrash\b|\bincompat\w*\b|\bconflict\b|\bissue\b",
    re.IGNORECASE,
)


def _random_delay(min_s: float = 2.0, max_s: float = 4.0) -> None:
    """Sleep for a random human-like delay."""
    delay = random.uniform(min_s, max_s)
    logger.debug("Human-like delay: %.2f seconds", delay)
    time.sleep(delay)


def _default_chromium_user_data_dir() -> str:
    """Return the default Chromium/Chrome user-data directory for the current OS."""
    if sys.platform == "win32":
        local_app_data = os.environ.get(
            "LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local")
        )
        return os.path.join(local_app_data, "Google", "Chrome", "User Data")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    # Linux / other POSIX
    return os.path.expanduser("~/.config/google-chrome")


def _parse_mod_id_from_url(url: str) -> Optional[int]:
    """Extract the Nexus mod ID from a URL, or ``None`` if not parseable."""
    match = re.search(r"/mods/(\d+)", url)
    return int(match.group(1)) if match else None


class NexusBrowserError(Exception):
    """Raised when the browser agent encounters an unrecoverable error."""


class NexusBrowser:
    """
    Playwright browser agent that navigates Nexus Mods pages as the
    authenticated user.

    Uses the user's existing Chromium profile (``launch_persistent_context``)
    so that the browser session, cookies, and login state are preserved.
    Chrome should **not** be running when this class is used, because two
    processes cannot share the same profile directory simultaneously.

    Parameters
    ----------
    user_data_dir:
        Path to the Chromium user-data directory.  Defaults to the standard
        Chrome location for the current OS.
    game_domain:
        Nexus Mods game domain slug (default: ``"skyrimspecialedition"``).
    headless:
        Run the browser in headless mode.  Defaults to ``False`` so the user
        can see what is happening.
    """

    # CSS selector candidates for the requirements list, tried in order.
    _REQ_CONTAINER_SELECTORS = [
        "ul.requirements li",
        "#tab-requirements li",
        ".mod-requirements li",
        "li.requirement",
        "[data-cy='requirements'] li",
    ]

    # CSS selector candidates for post / comment bodies, tried in order.
    _POST_BODY_SELECTORS = [
        ".posts-list .comment-content",
        ".comment-body",
        ".mq-comment-text",
        "article.comment p",
        ".forum-post-content",
    ]

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        game_domain: str = SKYRIM_SE_DOMAIN,
        headless: bool = False,
    ) -> None:
        self.user_data_dir = user_data_dir or _default_chromium_user_data_dir()
        self.game_domain = game_domain
        self.headless = headless
        self._playwright = None
        self._context: Optional["BrowserContext"] = None

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "NexusBrowser":
        self._start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop()

    def _start(self) -> None:
        """Launch Playwright and open the persistent browser context."""
        # Import here so Playwright is an optional dependency at module load.
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        logger.info("Starting Playwright with user data dir: %s", self.user_data_dir)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

    def _stop(self) -> None:
        """Close the browser context and stop Playwright."""
        if self._context is not None:
            logger.info("Closing browser context.")
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------
    # Main public method
    # ------------------------------------------------------------------

    def scrape_mod_page(self, mod_id: int) -> dict:
        """
        Navigate to a Nexus Mods page and extract structured data.

        Parameters
        ----------
        mod_id:
            The Nexus Mods mod ID to analyse.

        Returns
        -------
        dict
            A dictionary with the following keys:

            * ``mod_id`` – the requested mod ID
            * ``requirements`` – list of dicts compatible with
              :meth:`~src.database.manager.DatabaseManager.upsert_requirements`
              (keys: ``required_name``, ``required_url``,
              ``required_mod_id``, ``is_patch``)
            * ``patches`` – deduplicated list of patch-mention strings
              found in posts / comments
            * ``known_issues`` – deduplicated list of known-issue strings
              found in posts / comments
        """
        if self._context is None:
            raise NexusBrowserError(
                "Browser not started. Use NexusBrowser as a context manager."
            )

        mod_url = f"{NEXUS_BASE_URL}/{self.game_domain}/mods/{mod_id}"
        page: "Page" = self._context.new_page()
        try:
            logger.info("Navigating to mod page: %s", mod_url)
            page.goto(mod_url, wait_until="domcontentloaded", timeout=30_000)
            _random_delay()

            requirements = self._extract_requirements(page, mod_id)
            _random_delay()

            posts_data = self._extract_posts(page, mod_url)
        finally:
            page.close()

        return {
            "mod_id": mod_id,
            "requirements": requirements,
            "patches": posts_data["patches"],
            "known_issues": posts_data["known_issues"],
        }

    # ------------------------------------------------------------------
    # Requirements extraction
    # ------------------------------------------------------------------

    def _extract_requirements(self, page: "Page", mod_id: int) -> list[dict]:
        """Extract the requirements section from the current mod page."""
        reqs: list[dict] = []

        # Attempt to navigate to / expand the Requirements tab if present.
        try:
            req_tab: Optional["ElementHandle"] = page.query_selector(
                "a[href*='tab=requirements']"
            )
            if req_tab:
                req_tab.click()
                _random_delay(1.0, 2.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not click requirements tab: %s", exc)

        # Try each candidate selector until we find requirement items.
        items: list["ElementHandle"] = []
        for selector in self._REQ_CONTAINER_SELECTORS:
            found = page.query_selector_all(selector)
            if found:
                logger.debug(
                    "Found %d requirements via selector '%s'", len(found), selector
                )
                items = found
                break

        for item in items:
            text = (item.inner_text() or "").strip()
            if not text:
                continue

            # Extract href and mod ID from the first anchor inside the item.
            anchor: Optional["ElementHandle"] = item.query_selector("a[href]")
            href = ""
            req_mod_id: Optional[int] = None
            if anchor:
                href = anchor.get_attribute("href") or ""
                req_mod_id = _parse_mod_id_from_url(href)

            reqs.append(
                {
                    "required_name": text,
                    "required_url": href,
                    "required_mod_id": req_mod_id,
                    "is_patch": bool(_PATCH_RE.search(text)),
                }
            )

        logger.info("Extracted %d requirements for mod %d", len(reqs), mod_id)
        return reqs

    # ------------------------------------------------------------------
    # Posts / comments extraction
    # ------------------------------------------------------------------

    def _extract_posts(self, page: "Page", base_url: str) -> dict:
        """Navigate to the Posts tab and extract patch mentions and known issues."""
        patches: list[str] = []
        known_issues: list[str] = []

        posts_url = f"{base_url}?tab=posts"
        try:
            logger.info("Navigating to posts tab: %s", posts_url)
            page.goto(posts_url, wait_until="domcontentloaded", timeout=30_000)
            _random_delay()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not load posts tab for %s: %s", base_url, exc
            )
            return {"patches": patches, "known_issues": known_issues}

        # Collect comment/post body text using the first matching selector.
        comment_texts: list[str] = []
        for selector in self._POST_BODY_SELECTORS:
            elements = page.query_selector_all(selector)
            if elements:
                comment_texts = [
                    el.inner_text().strip()
                    for el in elements
                    if el.inner_text().strip()
                ]
                logger.debug(
                    "Found %d comments via selector '%s'",
                    len(comment_texts),
                    selector,
                )
                break

        for text in comment_texts:
            if _PATCH_RE.search(text):
                patches.extend(
                    line.strip()
                    for line in text.splitlines()
                    if line.strip() and _PATCH_RE.search(line)
                )
            if _ISSUE_RE.search(text):
                known_issues.extend(
                    line.strip()
                    for line in text.splitlines()
                    if line.strip() and _ISSUE_RE.search(line)
                )

        # Deduplicate while preserving first-seen order.
        patches = list(dict.fromkeys(patches))
        known_issues = list(dict.fromkeys(known_issues))

        logger.info(
            "Extracted %d patch mentions and %d known issues from posts",
            len(patches),
            len(known_issues),
        )
        return {"patches": patches, "known_issues": known_issues}
