"""
Playwright-based browser agent for extracting mod data from Nexus Mods pages.

Uses the user's existing Chromium browser session to navigate mod pages at
human-like speed (2-4 seconds between actions).  Extracts requirements,
posts/comments and patch mentions that are **not** available via the official
Nexus Mods REST API.

This is NOT mass scraping — it visits one mod at a time, at human speed,
using the user's own authenticated session.
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded so the rest of the app does not crash when Playwright
# is not installed.
_sync_playwright = None


def _import_playwright():
    """Import playwright lazily to avoid hard dependency at import time."""
    global _sync_playwright
    if _sync_playwright is None:
        try:
            from playwright.sync_api import sync_playwright as _sp
            _sync_playwright = _sp
        except ImportError:
            raise ImportError(
                "Playwright is not installed.  Run:\n"
                "  pip install playwright && python -m playwright install chromium"
            )
    return _sync_playwright


MOD_PAGE_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/{nexus_id}"


def _human_delay() -> int:
    """Return a random delay in ms to simulate human browsing speed."""
    return random.randint(2000, 4000)


def extract_mod_page_data(
    nexus_id: str,
    user_data_dir: Optional[str] = None,
    headless: bool = True,
) -> dict:
    """
    Open a mod page on Nexus Mods and extract structured data.

    Parameters
    ----------
    nexus_id : str
        The Nexus Mods mod ID (e.g. ``"2347"``).
    user_data_dir : str | None
        Path to a Chromium user-data directory that holds the user's
        authenticated session cookies.  When *None* the default profile
        is used (may not be logged in).
    headless : bool
        Whether to run the browser in headless mode.

    Returns
    -------
    dict
        ``{"requirements_html": str, "posts_html": str, "description_html": str}``
    """
    sp = _import_playwright()
    url = MOD_PAGE_URL.format(nexus_id=nexus_id)
    slow_mo = _human_delay()
    logger.info("Browsing mod page %s (slow_mo=%d ms)", url, slow_mo)

    result: dict = {
        "requirements_html": "",
        "posts_html": "",
        "description_html": "",
    }

    with sp() as pw:
        launch_kwargs: dict = {
            "headless": headless,
            "slow_mo": slow_mo,
        }
        if user_data_dir:
            context = pw.chromium.launch_persistent_context(
                user_data_dir,
                **launch_kwargs,
            )
            page = context.new_page()
        else:
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context()
            page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # --- Requirements section ---
            try:
                req_section = page.query_selector(
                    "#mod-page-tab-requirements, .tabbed-block .requirements"
                )
                if req_section:
                    result["requirements_html"] = req_section.inner_html()
            except Exception as exc:
                logger.warning("Could not extract requirements: %s", exc)

            # --- Description section ---
            try:
                desc_section = page.query_selector(
                    "#mod-page-tab-description, .tabbed-block .description"
                )
                if desc_section:
                    result["description_html"] = desc_section.inner_html()
            except Exception as exc:
                logger.warning("Could not extract description: %s", exc)

            # --- Posts / comments section ---
            try:
                posts_section = page.query_selector(
                    "#mod-page-tab-posts, .comments-container"
                )
                if posts_section:
                    result["posts_html"] = posts_section.inner_html()
            except Exception as exc:
                logger.warning("Could not extract posts: %s", exc)

        finally:
            page.close()
            context.close()

    return result
