"""Tests for the compatibility traffic-light status indicator."""

import json

import pytest

from src.analyzer.compatibility import (
    CompatibilityAnalyzer,
    compute_mod_statuses,
    _match_plugin_to_mod,
)
from src.database.manager import DatabaseManager
from src.mo2.reader import InstalledMod, MO2Profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_report(profile: MO2Profile) -> dict:
    """Return a clean report with no issues."""
    return {
        "missing_requirements": [],
        "loot_incompatibilities": [],
        "loot_warnings": [],
        "stats": {
            "total_mods": len(profile.mods),
            "enabled_mods": len(profile.enabled_mods),
            "missing_count": 0,
            "missing_patches": 0,
            "loot_incompatible": 0,
            "loot_warnings": 0,
        },
    }


def _make_profile(mods, load_order=None):
    """Create a profile from a list of (name, enabled) tuples."""
    return MO2Profile(
        profile_name="Test",
        mods=[InstalledMod(name=n, enabled=e) for n, e in mods],
        load_order=load_order or [],
    )


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_path=str(tmp_path / "test.db"))
    manager.connect()
    yield manager
    manager.close()


# ---------------------------------------------------------------------------
# compute_mod_statuses
# ---------------------------------------------------------------------------

class TestComputeModStatuses:
    """Verify the traffic-light derivation logic."""

    def test_all_green_when_no_issues(self):
        profile = _make_profile([("ModA", True), ("ModB", True)])
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods)
        assert result["ModA"] == "\U0001f7e2 OK"
        assert result["ModB"] == "\U0001f7e2 OK"

    def test_red_for_missing_required_dependency(self):
        profile = _make_profile([("SkyUI", True)])
        report = _empty_report(profile)
        report["missing_requirements"].append(
            {"mod_name": "SkyUI", "required_name": "SKSE64", "is_patch": False}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["SkyUI"] == "\U0001f534 ERROR"

    def test_yellow_for_missing_optional_patch(self):
        profile = _make_profile([("ModA", True)])
        report = _empty_report(profile)
        report["missing_requirements"].append(
            {"mod_name": "ModA", "required_name": "ModA-Patch", "is_patch": True}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["ModA"] == "\U0001f7e1 WARN"

    def test_red_overrides_yellow(self):
        """If a mod has both a missing patch and a missing required dep,
        the status should be red (error takes precedence over warning)."""
        profile = _make_profile([("ModA", True)])
        report = _empty_report(profile)
        report["missing_requirements"].extend([
            {"mod_name": "ModA", "required_name": "Patch", "is_patch": True},
            {"mod_name": "ModA", "required_name": "Core", "is_patch": False},
        ])
        result = compute_mod_statuses(report, profile.mods)
        assert result["ModA"] == "\U0001f534 ERROR"

    def test_disabled_mods_not_in_result(self):
        """Disabled mods should not appear in the statuses dict."""
        profile = _make_profile([("ModA", False)])
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods)
        assert "ModA" not in result

    def test_loot_incompatibility_maps_to_red(self):
        # Use a mod name that the fuzzy matcher can resolve to the plugin
        profile = _make_profile(
            [("USSEP", True)],
            load_order=["USSEP.esp", "Conflict.esp"],
        )
        report = _empty_report(profile)
        report["loot_incompatibilities"].append(
            {"mod_name": "USSEP.esp", "incompatible_with": "Conflict.esp"}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["USSEP"] == "\U0001f534 ERROR"

    def test_loot_warning_maps_to_yellow(self):
        profile = _make_profile(
            [("USSEP", True)],
            load_order=["USSEP.esp"],
        )
        report = _empty_report(profile)
        report["loot_warnings"].append(
            {"mod_name": "USSEP.esp", "message": "Needs update"}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["USSEP"] == "\U0001f7e1 WARN"

    def test_mixed_statuses(self):
        """Multiple mods with different status levels."""
        profile = _make_profile([
            ("GoodMod", True),
            ("WarnMod", True),
            ("BadMod", True),
            ("OffMod", False),
        ])
        report = _empty_report(profile)
        report["missing_requirements"].extend([
            {"mod_name": "WarnMod", "required_name": "OptionalPatch", "is_patch": True},
            {"mod_name": "BadMod", "required_name": "CoreDep", "is_patch": False},
        ])
        result = compute_mod_statuses(report, profile.mods)
        assert result["GoodMod"] == "\U0001f7e2 OK"
        assert result["WarnMod"] == "\U0001f7e1 WARN"
        assert result["BadMod"] == "\U0001f534 ERROR"
        assert "OffMod" not in result


# ---------------------------------------------------------------------------
# _match_plugin_to_mod
# ---------------------------------------------------------------------------

class TestMatchPluginToMod:
    def test_exact_match_with_extension(self):
        mods = [InstalledMod("SkyUI", enabled=True)]
        assert _match_plugin_to_mod("SkyUI.esp", mods) == "SkyUI"

    def test_no_match(self):
        mods = [InstalledMod("ModA", enabled=True)]
        assert _match_plugin_to_mod("CompletelyDifferent.esp", mods) is None

    def test_close_match(self):
        mods = [InstalledMod("USSEP", enabled=True)]
        assert _match_plugin_to_mod("USSEP.esp", mods) == "USSEP"


# ---------------------------------------------------------------------------
# Integration: full analyse -> status cycle
# ---------------------------------------------------------------------------

class TestAnalyseIntegration:
    """Run the real CompatibilityAnalyzer and verify compute_mod_statuses
    produces correct traffic lights from the resulting report."""

    def test_green_when_requirements_met(self, db):
        db.upsert_mod({"mod_id": 1, "name": "SkyUI", "summary": "",
                        "last_updated": "2024-01-01T00:00:00"})
        db.upsert_requirements(
            1, [{"required_name": "SKSE64", "is_patch": False, "required_url": ""}]
        )
        profile = _make_profile([("SkyUI", True), ("SKSE64", True)])
        analyser = CompatibilityAnalyzer(db)
        report = analyser.analyse(profile)
        statuses = compute_mod_statuses(report, profile.mods)
        assert statuses["SkyUI"] == "\U0001f7e2 OK"
        assert statuses["SKSE64"] == "\U0001f7e2 OK"

    def test_red_when_requirement_missing(self, db):
        db.upsert_mod({"mod_id": 2, "name": "SkyUI", "summary": "",
                        "last_updated": "2024-01-01T00:00:00"})
        db.upsert_requirements(
            2, [{"required_name": "SKSE64", "is_patch": False, "required_url": ""}]
        )
        profile = _make_profile([("SkyUI", True)])
        analyser = CompatibilityAnalyzer(db)
        report = analyser.analyse(profile)
        statuses = compute_mod_statuses(report, profile.mods)
        assert statuses["SkyUI"] == "\U0001f534 ERROR"

    def test_yellow_when_patch_missing(self, db):
        db.upsert_mod({"mod_id": 3, "name": "ModA", "summary": "",
                        "last_updated": "2024-01-01T00:00:00"})
        db.upsert_requirements(
            3, [{"required_name": "ModA-Patch", "is_patch": True, "required_url": ""}]
        )
        profile = _make_profile([("ModA", True)])
        analyser = CompatibilityAnalyzer(db)
        report = analyser.analyse(profile)
        statuses = compute_mod_statuses(report, profile.mods)
        assert statuses["ModA"] == "\U0001f7e1 WARN"

    def test_loot_incompatibility_status(self, db):
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            ("USSEP.esp", "[]", json.dumps(["Conflict.esp"]), "[]"),
        )
        db.conn.commit()
        profile = _make_profile(
            [("USSEP", True)],
            load_order=["USSEP.esp", "Conflict.esp"],
        )
        analyser = CompatibilityAnalyzer(db)
        report = analyser.analyse(profile)
        statuses = compute_mod_statuses(report, profile.mods)
        assert statuses["USSEP"] == "\U0001f534 ERROR"

    def test_loot_warning_status(self, db):
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            ("USSEP.esp", "[]", "[]", json.dumps(["[warn] Needs update"])),
        )
        db.conn.commit()
        profile = _make_profile(
            [("USSEP", True)],
            load_order=["USSEP.esp"],
        )
        analyser = CompatibilityAnalyzer(db)
        report = analyser.analyse(profile)
        statuses = compute_mod_statuses(report, profile.mods)
        assert statuses["USSEP"] == "\U0001f7e1 WARN"
