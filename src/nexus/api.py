"""
Nexus Mods API v1 wrapper.

Requires a personal API key that the user can obtain for free at:
https://www.nexusmods.com/users/myaccount?tab=api

Rate limits (free account):
  - 100 requests per day (daily limit)
  - 1 request per second

The game domain for Skyrim Special Edition is 'skyrimspecialedition'.
The numeric game_id used by the v1 API is 1704.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import requests

SKYRIM_SE_DOMAIN = "skyrimspecialedition"
SKYRIM_SE_GAME_ID = 1704
BASE_URL = "https://api.nexusmods.com/v1"


class RateLimitError(Exception):
    """Raised when the Nexus Mods API rate limit is reached."""


class NexusAPIError(Exception):
    """Raised for unexpected API responses."""


class NexusAPI:
    """Thin wrapper around the Nexus Mods v1 REST API."""

    def __init__(self, api_key: str, game_domain: str = SKYRIM_SE_DOMAIN):
        if not api_key:
            raise ValueError("An API key is required.")
        self.api_key = api_key
        self.game_domain = game_domain
        self._session = requests.Session()
        self._session.headers.update(
            {
                "apikey": self.api_key,
                "Accept": "application/json",
                "User-Agent": "AppNexus/1.0 (github.com/FacundoSu1986/App-nexus)",
            }
        )
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Ensure at least 1 second between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        self._throttle()
        try:
            response = self._session.get(url, params=params, timeout=15)
        finally:
            self._last_request_time = time.monotonic()

        if response.status_code == 429:
            raise RateLimitError(
                "Nexus Mods rate limit reached. "
                "Free accounts are limited to 100 requests/day."
            )
        if not response.ok:
            raise NexusAPIError(
                f"API request failed [{response.status_code}]: {response.text[:200]}"
            )
        return response.json()

    def _mod_url(self, endpoint: str) -> str:
        return f"{BASE_URL}/games/{self.game_domain}/{endpoint}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_mod(self, mod_id: int) -> dict:
        """Fetch metadata for a single mod and normalise into our internal format."""
        data = self._get(self._mod_url(f"mods/{mod_id}.json"))
        return self._normalise_mod(data)

    def get_mod_files(self, mod_id: int) -> list:
        """Return the list of file entries for a mod."""
        data = self._get(self._mod_url(f"mods/{mod_id}/files.json"))
        return data.get("files", [])

    def search_mods(self, query: str) -> list:
        """
        Full-text search via the Nexus Mods search endpoint.
        Returns a (possibly empty) list of normalised mod dicts.
        """
        url = f"https://search.nexusmods.com/mods"
        data = self._get(url, params={"terms": query, "game_id": SKYRIM_SE_GAME_ID})
        results = data.get("results", [])
        return [self._normalise_search_result(r) for r in results]

    def validate_api_key(self) -> dict:
        """Return user profile info to confirm the API key is valid."""
        return self._get(f"{BASE_URL}/users/validate.json")

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_mod(data: dict) -> dict:
        """Convert raw API response to the internal mod dict format."""
        return {
            "mod_id": data["mod_id"],
            "game_id": data.get("game_id", SKYRIM_SE_GAME_ID),
            "name": data.get("name", ""),
            "summary": data.get("summary", ""),
            "description": data.get("description", ""),
            "version": data.get("version", ""),
            "author": data.get("author", ""),
            "category_id": data.get("category_id"),
            "downloads": data.get("mod_downloads", 0),
            "endorsements": data.get("endorsement_count", 0),
            "picture_url": data.get("picture_url", ""),
            "mod_url": (
                f"https://www.nexusmods.com/skyrimspecialedition/mods/{data['mod_id']}"
            ),
            "last_scraped": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalise_search_result(result: dict) -> dict:
        """Normalise a search result entry (different shape from full mod data)."""
        return {
            "mod_id": result.get("mod_id", 0),
            "game_id": result.get("game_id", SKYRIM_SE_GAME_ID),
            "name": result.get("name", ""),
            "summary": result.get("description", ""),
            "description": "",
            "version": result.get("version", ""),
            "author": result.get("username", ""),
            "category_id": result.get("category_id"),
            "downloads": result.get("downloads", 0),
            "endorsements": result.get("endorsements", 0),
            "picture_url": result.get("thumbnail_url", ""),
            "mod_url": (
                f"https://www.nexusmods.com/skyrimspecialedition/mods/{result.get('mod_id', 0)}"
            ),
            "last_scraped": datetime.now(timezone.utc).isoformat(),
        }
