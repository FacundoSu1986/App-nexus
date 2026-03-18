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
import os
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
DOWNLOAD_PAGE_URL = (
    "https://www.nexusmods.com/skyrimspecialedition/mods/{nexus_id}"
    "?tab=files&file_id={file_id}"
)


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
                # Click the Requirements tab to expand its content
                req_tab = page.query_selector(
                    "li[class*='mod-page-tab'] a[href*='requirements'], "
                    "a:text('Requirements'), "
                    "#requirement-tab"
                )
                if req_tab:
                    req_tab.click()
                    page.wait_for_timeout(_human_delay())
                    logger.debug("Clicked Requirements tab")

                req_section = page.query_selector(
                    "#mod-page-tab-requirements, "
                    ".tabbed-block .requirements, "
                    "#tab-requirements, "
                    "div[class*='requirements']"
                )
                if req_section:
                    result["requirements_html"] = req_section.inner_html()
                    logger.debug(
                        "Requirements HTML extracted (%d chars): %.200s",
                        len(result["requirements_html"]),
                        result["requirements_html"],
                    )
                else:
                    logger.debug("Requirements selector matched nothing")
            except Exception as exc:
                logger.warning("Could not extract requirements: %s", exc)

            # --- Description section ---
            try:
                desc_section = page.query_selector(
                    "#mod-page-tab-description, "
                    ".tabbed-block .description, "
                    "#tab-description, "
                    "div[class*='mod-desc']"
                )
                if desc_section:
                    result["description_html"] = desc_section.inner_html()
                    logger.debug(
                        "Description HTML extracted (%d chars): %.200s",
                        len(result["description_html"]),
                        result["description_html"],
                    )
                else:
                    logger.debug("Description selector matched nothing")
            except Exception as exc:
                logger.warning("Could not extract description: %s", exc)

            # --- Posts / comments section ---
            try:
                # Click the Posts tab to expand its content
                posts_tab = page.query_selector(
                    "li[class*='mod-page-tab'] a[href*='posts'], "
                    "a:text('Posts'), "
                    "#posts-tab"
                )
                if posts_tab:
                    posts_tab.click()
                    page.wait_for_timeout(_human_delay())
                    logger.debug("Clicked Posts tab")

                posts_section = page.query_selector(
                    "#mod-page-tab-posts, "
                    ".comments-container, "
                    "#tab-posts, "
                    "div[class*='comment']"
                )
                if posts_section:
                    result["posts_html"] = posts_section.inner_html()
                    logger.debug(
                        "Posts HTML extracted (%d chars): %.200s",
                        len(result["posts_html"]),
                        result["posts_html"],
                    )
                else:
                    logger.debug("Posts selector matched nothing")
            except Exception as exc:
                logger.warning("Could not extract posts: %s", exc)

        finally:
            page.close()
            context.close()

    return result


def download_mod_file(
    nexus_id: str,
    file_id: str,
    output_dir: str,
    user_data_dir: Optional[str] = None,
    headless: bool = True,
) -> Optional[str]:
    """
    Download a mod archive from Nexus Mods using the free-user slow download.

    Parameters
    ----------
    nexus_id : str
        The Nexus Mods mod ID (e.g. ``"2347"``).
    file_id : str
        The Nexus Mods file ID for the specific archive.
    output_dir : str
        Directory where the downloaded file will be saved.
        Created automatically if it does not exist.
    user_data_dir : str | None
        Path to a Chromium user-data directory that holds the user's
        authenticated session cookies.  When *None* the default profile
        is used (may not be logged in).
    headless : bool
        Whether to run the browser in headless mode.

    Returns
    -------
    str | None
        Absolute path of the downloaded file, or ``None`` on failure.
    """
    sp = _import_playwright()
    url = DOWNLOAD_PAGE_URL.format(nexus_id=nexus_id, file_id=file_id)
    slow_mo = _human_delay()
    logger.info("Navigating to download page %s (slow_mo=%d ms)", url, slow_mo)

    os.makedirs(output_dir, exist_ok=True)

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
    except ImportError:
        PlaywrightTimeout = TimeoutError

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
            logger.info("Page loaded for mod %s file %s", nexus_id, file_id)

            try:
                slow_btn = page.wait_for_selector(
                    "button#slowDownloadButton, "
                    "a:has-text('Slow'), "
                    "button:has-text('Slow download')",
                    timeout=15000,
                )
            except PlaywrightTimeout:
                logger.warning(
                    "Slow Download button not found on page for mod %s file %s "
                    "— user may not be logged in or Premium may be required",
                    nexus_id,
                    file_id,
                )
                return None

            logger.info("Clicking Slow Download button...")
            logger.info("Waiting for 5-second countdown...")
            try:
                with page.expect_download(timeout=60000) as download_info:
                    slow_btn.click()

                download = download_info.value
                filename = os.path.basename(download.suggested_filename)
                dest = os.path.join(output_dir, filename)
                download.save_as(dest)
                abs_path = os.path.abspath(dest)
                logger.info("Download saved to %s", abs_path)
                return abs_path
            except PlaywrightTimeout:
                logger.warning(
                    "Download timed out for mod %s file %s",
                    nexus_id,
                    file_id,
                )
                return None
            except (ConnectionError, OSError) as exc:
                logger.warning(
                    "Network error during download for mod %s file %s: %s",
                    nexus_id,
                    file_id,
                    exc,
                )
                return None
            except Exception as exc:
                logger.warning(
                    "Download failed for mod %s file %s: %s",
                    nexus_id,
                    file_id,
                    exc,
                )
                return None

        except (ConnectionError, OSError) as exc:
            logger.warning(
                "Network error navigating to download page for mod %s file %s: %s",
                nexus_id,
                file_id,
                exc,
            )
            return None
        except Exception as exc:
            logger.warning(
                "Error navigating to download page for mod %s file %s: %s",
                nexus_id,
                file_id,
                exc,
            )
            return None
        finally:
            page.close()
            context.close()
