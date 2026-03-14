"""
Mod compatibility and completeness analyser.

Given the user's installed mod list (from MO2) and the cached database of mod
metadata (requirements, incompatibilities, load-order rules), this module
produces a structured report that the GUI can display.

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
    "incompatibilities": [
        {
            "mod_name":           str,
            "incompatible_name":  str,
            "reason":             str,
        },
        ...
    ],
    "load_order_violations": [
        {
            "mod_name":       str,
            "rule_type":      str,  # 'AFTER' | 'BEFORE'
            "target_name":    str,
            "current_index":  int,
            "target_index":   int,
        },
        ...
    ],
    "stats": {
        "total_mods":          int,
        "enabled_mods":        int,
        "missing_count":       int,
        "missing_patches":     int,
        "incompatible_count":  int,
        "violations_count":    int,
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
        incompatibilities: list = []
        load_order_violations: list = []

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

            # ---- Incompatibilities --------------------------------------
            for inc in self.db.get_incompatibilities(mod_id):
                if _mod_in_list(inc["incompatible_name"], enabled_names):
                    incompatibilities.append(
                        {
                            "mod_name": mod.name,
                            "incompatible_name": inc["incompatible_name"],
                            "reason": inc.get("reason", ""),
                        }
                    )

            # ---- Load-order rules ---------------------------------------
            for rule in self.db.get_load_order_rules(mod_id):
                violation = self._check_load_order_rule(
                    mod.name,
                    rule,
                    profile.load_order,
                )
                if violation:
                    load_order_violations.append(violation)

        missing_patches = sum(
            1 for m in missing_requirements if m["is_patch"]
        )

        return {
            "missing_requirements": missing_requirements,
            "incompatibilities": incompatibilities,
            "load_order_violations": load_order_violations,
            "stats": {
                "total_mods": len(profile.mods),
                "enabled_mods": len(profile.enabled_mods),
                "missing_count": len(missing_requirements),
                "missing_patches": missing_patches,
                "incompatible_count": len(incompatibilities),
                "violations_count": len(load_order_violations),
            },
        }

    # ------------------------------------------------------------------
    # Load-order helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_load_order_rule(
        mod_name: str, rule: dict, load_order: list
    ) -> dict | None:
        """
        Return a violation dict if the rule is broken, or ``None`` otherwise.

        Rules:
        - ``AFTER target`` → mod_name must appear *after* target in load_order
        - ``BEFORE target`` → mod_name must appear *before* target in load_order
        """
        target_name = rule["target_mod_name"]
        rule_type = rule["rule_type"]

        mod_idx = next(
            (i for i, p in enumerate(load_order) if _similar(mod_name, p)), None
        )
        target_idx = next(
            (i for i, p in enumerate(load_order) if _similar(target_name, p)), None
        )

        if mod_idx is None or target_idx is None:
            return None  # one of the plugins is not in the load order → skip

        violated = (rule_type == "AFTER" and mod_idx < target_idx) or (
            rule_type == "BEFORE" and mod_idx > target_idx
        )
        if not violated:
            return None

        return {
            "mod_name": mod_name,
            "rule_type": rule_type,
            "target_name": target_name,
            "current_index": mod_idx,
            "target_index": target_idx,
        }
