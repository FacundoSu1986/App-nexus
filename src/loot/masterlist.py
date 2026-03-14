"""
LOOT masterlist downloader and parser.

Downloads the public LOOT masterlist for Skyrim SE, parses the YAML to
extract per-plugin metadata (requirements, incompatibilities, messages),
and stores it in the local SQLite database via :class:`DatabaseManager`.

Masterlist data: LOOT (loot.github.io) — CC BY-NC-SA 4.0
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests
import yaml

if TYPE_CHECKING:
    from src.database.manager import DatabaseManager

logger = logging.getLogger(__name__)

MASTERLIST_URL = (
    "https://raw.githubusercontent.com/loot/skyrimse/main/masterlist.yaml"
)


def download_masterlist(url: str = MASTERLIST_URL, timeout: int = 60) -> str:
    """Download the LOOT masterlist YAML and return the raw text."""
    logger.info("Downloading LOOT masterlist from %s", url)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
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
    count = 0
    for entry in entries:
        db.upsert_loot_entry(entry)
        count += 1
    return count


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

def _extract_requirements(plugin: dict) -> list[str]:
    """Return a list of required plugin names from a masterlist plugin entry."""
    reqs: list[str] = []
    for item in plugin.get("req", []):
        if isinstance(item, str):
            reqs.append(item)
        elif isinstance(item, dict) and "name" in item:
            reqs.append(str(item["name"]))
    return reqs


def _extract_incompatibilities(plugin: dict) -> list[str]:
    """Return a list of incompatible plugin names."""
    incs: list[str] = []
    for item in plugin.get("inc", []):
        if isinstance(item, str):
            incs.append(item)
        elif isinstance(item, dict) and "name" in item:
            incs.append(str(item["name"]))
    return incs


def _extract_messages(plugin: dict) -> list[str]:
    """Return a list of warning/info messages."""
    msgs: list[str] = []
    for item in plugin.get("msg", []):
        if isinstance(item, str):
            msgs.append(item)
        elif isinstance(item, dict):
            # Messages in the masterlist often use a structure like:
            #   - type: warn
            #     content: "Some warning text"
            content = item.get("content", "")
            if content:
                msg_type = item.get("type", "say")
                msgs.append(f"[{msg_type}] {content}")
    return msgs
