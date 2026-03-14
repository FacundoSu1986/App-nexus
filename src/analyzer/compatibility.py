"""
Mod compatibility and completeness analyser.

Given the user's installed mod list (from MO2) and the cached database of mod
metadata (requirements), this module produces a structured report that the GUI
can display.

Report structure
----------------
{
    "missing_requirements": [
        {
            "mod_name":      str,   # installed mod that has the requirement
            "required_name": str,   # the mod that is missing
            "required_url":  str,
            "is_patch":      bool,
        },
        ...
    ],
    "stats": {
        "total_mods":          int,
        "enabled_mods":        int,
        "missing_count":       int,
        "missing_patches":     int,
    }
}
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.manager import DatabaseManager
    from src.mo2.reader import MO2Profile

# Threshold chosen empirically: at 0.82 common Skyrim mod names that differ by
# one word (e.g. "SkyUI" vs "SkyUI SE") are still considered the same mod, while
# clearly unrelated names (e.g. "SKSE64" vs "SkyUI") score well below 0.82.
# Plugin extensions (.esp/.esm/.esl) are stripped before comparison so that a mod
# named "SkyUI" matches the plugin "SkyUI.esp" in the load order.
_SIMILARITY_THRESHOLD = 0.82
_PLUGIN_EXTS = frozenset({".esp", ".esm", ".esl"})


def _strip_plugin_ext(name: str) -> str:
    """Remove .esp / .esm / .esl extension from a plugin filename if present."""
    lower = name.lower()
    for ext in _PLUGIN_EXTS:
        if lower.endswith(ext):
            return name[: -len(ext)]
    return name


def _similar(a: str, b: str) -> bool:
    """Return True when two mod names are similar enough to be considered equal.

    Strips plugin extensions before comparing so that a mod named ``SkyUI``
    can match the plugin ``SkyUI.esp`` in the load order.
    """
    a = _strip_plugin_ext(a.lower().strip())
    b = _strip_plugin_ext(b.lower().strip())
    if a == b:
        return True
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio >= _SIMILARITY_THRESHOLD


def _mod_in_list(mod_name: str, name_list: list) -> bool:
    """Return True if ``mod_name`` is present (fuzzy) in ``name_list``."""
    for name in name_list:
        if _similar(mod_name, name):
            return True
    return False


class CompatibilityAnalyzer:
    """Compares the user's installed mods against the cached database rules."""

    def __init__(self, db: "DatabaseManager"):
        self.db = db

    def analyse(self, profile: "MO2Profile") -> dict:
        """
        Run a full compatibility analysis and return the report dict.

        Parameters
        ----------
        profile:
            The MO2 profile to analyse.
        """
        enabled_names = profile.enabled_mod_names
        missing_requirements: list = []
        loot_incompatibilities: list = []
        loot_warnings: list = []

        for mod in profile.enabled_mods:
            db_results = self.db.search_mods_by_name(mod.name)
            if not db_results:
                continue
            db_mod = db_results[0]
            mod_id = db_mod["mod_id"]

            # ---- Missing requirements / patches -------------------------
            for req in self.db.get_requirements(mod_id):
                if not _mod_in_list(req["required_name"], enabled_names):
                    missing_requirements.append(
                        {
                            "mod_name": mod.name,
                            "required_name": req["required_name"],
                            "required_url": req.get("required_url", ""),
                            "is_patch": bool(req.get("is_patch", False)),
                        }
                    )

        # ---- LOOT incompatibilities & warnings --------------------------
        for plugin_name in profile.load_order:
            loot_entry = self.db.get_loot_entry(plugin_name)
            if not loot_entry:
                continue

            for inc_name in loot_entry.get("inc", []):
                if _mod_in_list(inc_name, profile.load_order):
                    loot_incompatibilities.append({
                        "mod_name": plugin_name,
                        "incompatible_with": inc_name,
                    })

            for msg in loot_entry.get("msg", []):
                loot_warnings.append({
                    "mod_name": plugin_name,
                    "message": msg,
                })

        missing_patches = sum(
            1 for m in missing_requirements if m["is_patch"]
        )

        return {
            "missing_requirements": missing_requirements,
            "loot_incompatibilities": loot_incompatibilities,
            "loot_warnings": loot_warnings,
            "stats": {
                "total_mods": len(profile.mods),
                "enabled_mods": len(profile.enabled_mods),
                "missing_count": len(missing_requirements),
                "missing_patches": missing_patches,
                "loot_incompatible": len(loot_incompatibilities),
                "loot_warnings": len(loot_warnings),
            },
        }
