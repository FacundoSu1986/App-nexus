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

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests import Response, Session
from requests.exceptions import RequestException, Timeout

logger = logging.getLogger(__name__)

SKYRIM_SE_DOMAIN = "skyrimspecialedition"
SKYRIM_SE_GAME_ID = 1704
BASE_URL = "https://api.nexusmods.com/v1"


class RateLimitError(Exception):
    """Raised when the Nexus Mods API rate limit is reached."""


class NexusAPIError(Exception):
    """Raised for unexpected API responses or network errors."""


class NexusAPI:
    """Thin wrapper around the Nexus Mods v1 REST API."""

    def __init__(self, api_key: str, game_domain: str = SKYRIM_SE_DOMAIN) -> None:
        if not api_key:
            raise ValueError("An API key is required.")
        self.api_key = api_key
        self.game_domain = game_domain
        self._session: Session = requests.Session()
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

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform an HTTP request with throttling and error handling."""
        self._throttle()
        logger.info("HTTP %s %s params=%s", method, url, params)

        try:
            response: Response = self._session.request(
                method=method,
                url=url,
                params=params,
                timeout=15,
            )
        except Timeout as exc:
            logger.error("Timeout calling %s: %s", url, exc)
            raise NexusAPIError(f"Request to {url} timed out") from exc
        except RequestException as exc:
            logger.error("Network error calling %s: %s", url, exc)
            raise NexusAPIError(f"Network error calling {url}: {exc}") from exc
        finally:
            self._last_request_time = time.monotonic()

        logger.info("Response status=%d for %s", response.status_code, url)

        if response.status_code == 429:
            logger.error("Rate limit reached for %s", url)
            raise RateLimitError(
                "Nexus Mods rate limit reached. "
                "Free accounts are limited to 100 requests/day."
            )

        if not response.ok:
            text_preview = response.text[:200] if response.text else ""
            logger.error("API error [%d]: %s", response.status_code, text_preview)
            raise NexusAPIError(
                f"API request failed [{response.status_code}]: {text_preview}"
            )

        return response.json()

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Convenience wrapper for GET requests."""
        return self._request("GET", url, params=params)

    def _mod_url(self, endpoint: str) -> str:
        return f"{BASE_URL}/games/{self.game_domain}/{endpoint}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_mod(self, mod_id: int) -> Dict[str, Any]:
        """Fetch metadata for a single mod and normalise into our internal format."""
        data = self._get(self._mod_url(f"mods/{mod_id}.json"))
        return self._normalise_mod(data)

    def get_mod_files(self, mod_id: int) -> List[Dict[str, Any]]:
        """Return the list of file entries for a mod."""
        data = self._get(self._mod_url(f"mods/{mod_id}/files.json"))
        return data.get("files", [])

    def get_mod_requirements(self, mod_id: int) -> List[Dict[str, Any]]:
        """GET /games/{game_domain}/mods/{mod_id}/requirements.json

        Returns a list of normalised requirement dicts ready for
        ``DatabaseManager.upsert_requirements``.
        """
        url = self._mod_url(f"mods/{mod_id}/requirements.json")
        raw_data = self._get(url)
        normalized = []
        for req in raw_data:
            req_mod_id = req.get("mod_id")
            name = req.get("name", "Unknown")
            normalized.append({
                "required_mod_id": req_mod_id,
                "required_name": name,
                "required_url": (
                    f"https://www.nexusmods.com/{self.game_domain}/mods/{req_mod_id}"
                    if req_mod_id else ""
                ),
                "is_patch": bool(
                    re.search(r"\bpatch\b|\bfix\b|\bcompat", name, re.IGNORECASE)
                ),
            })
        return normalized

    def search_mods(self, query: str) -> List[Dict[str, Any]]:
        """
        Full-text search via the Nexus Mods search endpoint.
        Returns a (possibly empty) list of normalised mod dicts.
        """
        url = "https://search.nexusmods.com/mods"
        data = self._get(url, params={"terms": query, "game_id": SKYRIM_SE_GAME_ID})
        results = data.get("results", [])
        return [self._normalise_search_result(r) for r in results]

    def validate_api_key(self) -> Dict[str, Any]:
        """Return user profile info to confirm the API key is valid."""
        return self._get(f"{BASE_URL}/users/validate.json")

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalise_mod(self, data: Dict[str, Any]) -> Dict[str, Any]:
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
                f"https://www.nexusmods.com/{self.game_domain}/mods/{data['mod_id']}"
            ),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def _normalise_search_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
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
                f"https://www.nexusmods.com/{self.game_domain}/mods/{result.get('mod_id', 0)}"
            ),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
