"""
LOOT masterlist downloader and parser.

Downloads the public LOOT masterlist for Skyrim SE, parses the YAML to
extract per-plugin metadata (requirements, incompatibilities, messages),
and stores it in the local SQLite database via :class:`DatabaseManager`.

Masterlist data: LOOT (loot.github.io) — CC BY-NC-SA 4.0
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import requests
import yaml

if TYPE_CHECKING:
    from src.database.manager import DatabaseManager

logger = logging.getLogger(__name__)

MASTERLIST_URL = (
    "https://raw.githubusercontent.com/loot/skyrimse/v0.17/masterlist.yaml"
)


def download_masterlist(url: str = MASTERLIST_URL, timeout: int = 60) -> str:
    """Download the LOOT masterlist YAML and return the raw text."""
    logger.info("Downloading LOOT masterlist from %s", url)
    response = requests.get(url, timeout=timeout)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"Failed to download LOOT masterlist from {url} "
            f"(HTTP {response.status_code})"
        ) from exc
    return response.text


def parse_masterlist(raw_yaml: str) -> list[dict]:
    """Parse LOOT masterlist YAML and return a list of plugin entries.

    Each returned dict has the keys:

    * **name** – plugin filename (e.g. ``SkyUI_SE.esp``)
    * **req** – list of requirement plugin names
    * **inc** – list of incompatible plugin names
    * **msg** – list of warning/message strings
    """
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return []

    entries: list[dict] = []
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue

        name = plugin.get("name", "")
        if not name:
            continue

        req = _extract_requirements(plugin)
        inc = _extract_incompatibilities(plugin)
        msg = _extract_messages(plugin)

        entries.append({
            "name": str(name),
            "req": req,
            "inc": inc,
            "msg": msg,
        })

    return entries


def save_to_database(entries: list[dict], db: "DatabaseManager") -> int:
    """Persist parsed masterlist entries into the database.

    Returns the number of entries saved.
    """
    db.upsert_loot_entries(entries)
    return len(entries)


def update_masterlist(db: "DatabaseManager") -> int:
    """Download, parse, and store the LOOT masterlist in one step.

    Returns the number of plugin entries stored.
    """
    raw = download_masterlist()
    entries = parse_masterlist(raw)
    return save_to_database(entries, db)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"%\d+%")
_TAG_RE = re.compile(r"^\[(say|warn|info)\]\s*", re.IGNORECASE)


def clean_loot_message(text: str | list | dict) -> str:
    """Return a clean, human-readable string from a LOOT message.

    Handles several raw formats that can appear in masterlist data:

    * A plain string (returned cleaned).
    * A ``list`` of dicts such as ``[{'lang': 'en', 'text': '…'}]`` –
      the ``'text'`` value of the first English entry is extracted.
    * A ``dict`` with a ``'text'`` key – the value is extracted.
    * Leading ``[say]``, ``[warn]``, ``[info]`` tags are stripped.
    * LOOT placeholder variables (``%1%``, ``%2%``, …) are replaced with
      ``[see Nexus page]``, and resulting double-spaces are collapsed.
    """
    # ── Unwrap list/dict structures ───────────────────────────────
    if isinstance(text, list):
        # e.g. [{'lang': 'en', 'text': '…'}, {'lang': 'fr', 'text': '…'}]
        for item in text:
            if isinstance(item, dict) and item.get("text"):
                text = str(item["text"])
                break
        else:
            # Fall back to stringifying the first element (or empty)
            text = str(text[0]) if text else ""

    if isinstance(text, dict):
        text = str(text.get("text", "") or text.get("content", ""))

    text = str(text)

    # ── Strip leading [say] / [warn] / [info] tags ────────────────
    text = _TAG_RE.sub("", text)

    # ── Replace LOOT placeholders and tidy whitespace ─────────────
    cleaned = _PLACEHOLDER_RE.sub("[see Nexus page]", text)
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned.strip()


def _extract_requirements(plugin: dict) -> list[str]:
    """Return a list of required plugin names from a masterlist plugin entry."""
    raw = plugin.get("req", [])
    if not isinstance(raw, list):
        return []
    reqs: list[str] = []
    for item in raw:
        if isinstance(item, str):
            reqs.append(item)
        elif isinstance(item, dict) and "name" in item:
            reqs.append(str(item["name"]))
    return reqs


def _extract_incompatibilities(plugin: dict) -> list[str]:
    """Return a list of incompatible plugin names."""
    raw = plugin.get("inc", [])
    if not isinstance(raw, list):
        return []
    incs: list[str] = []
    for item in raw:
        if isinstance(item, str):
            incs.append(item)
        elif isinstance(item, dict) and "name" in item:
            incs.append(str(item["name"]))
    return incs


def _extract_messages(plugin: dict) -> list[str]:
    """Return a list of warning/info messages."""
    raw = plugin.get("msg", [])
    if not isinstance(raw, list):
        return []
    msgs: list[str] = []
    for item in raw:
        if isinstance(item, str):
            msgs.append(clean_loot_message(item))
        elif isinstance(item, dict):
            # Messages in the masterlist often use a structure like:
            #   - type: warn
            #     content: "Some warning text"
            # or the multi-language form:
            #   - lang: en
            #     text: "Some warning text"
            content = item.get("content") or item.get("text", "")
            if content:
                msgs.append(clean_loot_message(str(content)))
        elif isinstance(item, list):
            # A list of language-specific dicts, e.g.
            # [{'lang': 'en', 'text': '…'}, {'lang': 'fr', 'text': '…'}]
            msgs.append(clean_loot_message(item))
    return msgs
