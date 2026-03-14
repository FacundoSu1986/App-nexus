"""
Web scraper for Nexus Mods mod pages.

Complements the REST API by extracting data that is not available via the
API endpoints:
  - The "Requirements" tab (hard/soft dependencies and recommended patches)
  - The "Posts" / "Bugs" tabs (user-reported issues)
  - Incompatibility warnings listed in the description

Usage example::

    scraper = NexusScraper()
    requirements = scraper.get_requirements(mod_id=3328)   # SKSE64
    issues       = scraper.get_issues(mod_id=3328, max_pages=2)
"""

import re
import time
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

NEXUS_BASE = "https://www.nexusmods.com"
SKYRIM_SE_PATH = "/skyrimspecialedition/mods"

_PATCH_KEYWORDS = re.compile(
    r"\bpatch\b|\bfix\b|\bcompat", re.IGNORECASE
)
_INCOMPAT_KEYWORDS = re.compile(
    r"incompatible|conflict|do not use|not compatible", re.IGNORECASE
)


class NexusScraper:
    """Scrapes mod pages on Nexus Mods that are not covered by the API."""

    def __init__(self, delay: float = 2.0):
        """
        Parameters
        ----------
        delay:
            Minimum seconds between HTTP requests (be polite to Nexus).
        """
        self.delay = delay
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "AppNexus/1.0 (github.com/FacundoSu1986/App-nexus)"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _get(self, url: str, params: Optional[dict] = None) -> BeautifulSoup:
        self._throttle()
        try:
            resp = self._session.get(url, params=params, timeout=20)
        finally:
            self._last_request_time = time.monotonic()
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _mod_page_url(self, mod_id: int) -> str:
        return f"{NEXUS_BASE}{SKYRIM_SE_PATH}/{mod_id}"

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    def get_requirements(self, mod_id: int) -> list:
        """
        Scrape the Requirements tab of a mod page.

        Returns a list of dicts::

            {
                "required_name": str,
                "required_url":  str,   # full URL or ""
                "is_patch":      bool,
            }
        """
        url = self._mod_page_url(mod_id)
        soup = self._get(url)
        return self._parse_requirements(soup)

    def _parse_requirements(self, soup: BeautifulSoup) -> list:
        requirements = []

        # Nexus renders requirements inside a section with id "requirements"
        # or inside a tab panel labelled "Requirements".
        req_section = soup.find(id="requirements") or soup.find(
            "div", {"data-tab": "requirements"}
        )
        if req_section is None:
            # Fall back: look for any <ul> under a heading that says "Requirements"
            for heading in soup.find_all(["h2", "h3", "h4"]):
                if "requirement" in heading.get_text(strip=True).lower():
                    req_section = heading.find_next_sibling()
                    break

        if req_section is None:
            return requirements

        for link in req_section.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True)
            if not name:
                continue
            full_url = href if href.startswith("http") else urljoin(NEXUS_BASE, href)
            requirements.append(
                {
                    "required_name": name,
                    "required_url": full_url,
                    "is_patch": bool(_PATCH_KEYWORDS.search(name)),
                }
            )

        return requirements

    # ------------------------------------------------------------------
    # Issues / posts / bugs
    # ------------------------------------------------------------------

    def get_issues(self, mod_id: int, max_pages: int = 3) -> list:
        """
        Scrape the Bugs/Posts tab for user-reported issues.

        Returns a list of dicts::

            {
                "title":     str,
                "body":      str,
                "author":    str,
                "posted_at": str,  # ISO-like string or ""
                "url":       str,
            }
        """
        issues: list = []
        for page in range(1, max_pages + 1):
            url = f"{self._mod_page_url(mod_id)}?tab=bugs"
            soup = self._get(url, params={"page": page})
            page_issues = self._parse_issues(soup, mod_id)
            if not page_issues:
                break
            issues.extend(page_issues)
        return issues

    def _parse_issues(self, soup: BeautifulSoup, mod_id: int) -> list:
        issues = []
        # Bug reports are typically inside a list with class "bugs-list"
        # or individual <article>/<li> elements.
        container = (
            soup.find("ul", class_=re.compile(r"bugs", re.I))
            or soup.find("div", id=re.compile(r"bugs", re.I))
            or soup.find("div", class_=re.compile(r"comments", re.I))
        )
        if container is None:
            return issues

        for item in container.find_all(["li", "article"], recursive=False):
            title_tag = item.find(["h3", "h4", "a"])
            title = title_tag.get_text(strip=True) if title_tag else "Untitled"

            body_tag = item.find("p")
            body = body_tag.get_text(strip=True) if body_tag else ""

            author_tag = item.find(class_=re.compile(r"author|username", re.I))
            author = author_tag.get_text(strip=True) if author_tag else ""

            time_tag = item.find("time")
            posted_at = time_tag.get("datetime", "") if time_tag else ""

            link_tag = item.find("a", href=True)
            url = ""
            if link_tag:
                href = link_tag["href"]
                url = href if href.startswith("http") else urljoin(NEXUS_BASE, href)

            issues.append(
                {
                    "title": title,
                    "body": body,
                    "author": author,
                    "posted_at": posted_at,
                    "url": url,
                }
            )
        return issues

    # ------------------------------------------------------------------
    # Incompatibilities (parsed from description)
    # ------------------------------------------------------------------

    def get_incompatibilities_from_description(
        self, description_html: str
    ) -> list:
        """
        Parse incompatibility mentions from a mod's HTML description.

        Returns a list of dicts::

            {
                "incompatible_name": str,
                "incompatible_mod_id": None,  # cannot resolve without extra lookup
                "reason": str,
            }
        """
        soup = BeautifulSoup(description_html, "lxml")
        incompatibilities = []
        for tag in soup.find_all(string=_INCOMPAT_KEYWORDS):
            # Walk up to the nearest block-level element for wider context
            context = tag.parent
            for _ in range(3):
                if context is None:
                    break
                if context.name in {"p", "li", "div", "section", "article"}:
                    break
                context = context.parent

            if context is None:
                continue

            text = context.get_text(separator=" ", strip=True)
            # Try to find a linked mod name near this mention
            link = context.find("a", href=True)
            name = link.get_text(strip=True) if link else text[:80]
            incompatibilities.append(
                {
                    "incompatible_name": name,
                    "incompatible_mod_id": None,
                    "reason": text[:200],
                }
            )
        return incompatibilities
