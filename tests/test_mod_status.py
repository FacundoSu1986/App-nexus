"""Tests for the compatibility traffic-light status indicator."""

import json

import pytest

from src.analyzer.compatibility import (
    CompatibilityAnalyzer,
    compute_mod_statuses,
    _match_plugin_to_mod,
    _version_is_older,
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
        assert result["ModA"] == "\u2714 OK"
        assert result["ModB"] == "\u2714 OK"

    def test_red_for_missing_required_dependency(self):
        profile = _make_profile([("SkyUI", True)])
        report = _empty_report(profile)
        report["missing_requirements"].append(
            {"mod_name": "SkyUI", "required_name": "SKSE64", "is_patch": False}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["SkyUI"] == "\u2718 ERROR"

    def test_yellow_for_missing_optional_patch(self):
        profile = _make_profile([("ModA", True)])
        report = _empty_report(profile)
        report["missing_requirements"].append(
            {"mod_name": "ModA", "required_name": "ModA-Patch", "is_patch": True}
        )
        result = compute_mod_statuses(report, profile.mods)
        assert result["ModA"] == "\u26a0 WARN"

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
        assert result["ModA"] == "\u2718 ERROR"

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
        assert result["USSEP"] == "\u2718 ERROR"

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
        assert result["USSEP"] == "\u26a0 WARN"

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
        assert result["GoodMod"] == "\u2714 OK"
        assert result["WarnMod"] == "\u26a0 WARN"
        assert result["BadMod"] == "\u2718 ERROR"
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
        assert statuses["SkyUI"] == "\u2714 OK"
        assert statuses["SKSE64"] == "\u2714 OK"

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
        assert statuses["SkyUI"] == "\u2718 ERROR"

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
        assert statuses["ModA"] == "\u26a0 WARN"

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
        assert statuses["USSEP"] == "\u2718 ERROR"

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
        assert statuses["USSEP"] == "\u26a0 WARN"


# ---------------------------------------------------------------------------
# Populate mod list status column: simulates _populate_mod_list logic
# ---------------------------------------------------------------------------

class TestPopulateModListStatuses:
    """Verify that the status column values produced by the
    _populate_mod_list logic match the expected traffic-light
    indicators after an analysis report is available."""

    @staticmethod
    def _status_column(mod, statuses):
        """Reproduce the status assignment from MainWindow._populate_mod_list."""
        if not mod.enabled:
            return "\u2718 OFF"
        return statuses.get(mod.name, "\u2714 ON")

    def test_traffic_lights_after_analyse(self):
        """After analysis, every enabled mod should show a traffic light,
        never the plain '✔ ON' fallback."""
        profile = _make_profile([
            ("GoodMod", True),
            ("WarnMod", True),
            ("BadMod", True),
            ("DisabledMod", False),
        ])
        report = _empty_report(profile)
        report["missing_requirements"].extend([
            {"mod_name": "WarnMod", "required_name": "Patch", "is_patch": True},
            {"mod_name": "BadMod", "required_name": "Core", "is_patch": False},
        ])
        statuses = compute_mod_statuses(report, profile.mods)

        results = {
            mod.name: self._status_column(mod, statuses)
            for mod in profile.mods
        }
        assert results["GoodMod"] == "\u2714 OK"
        assert results["WarnMod"] == "\u26a0 WARN"
        assert results["BadMod"] == "\u2718 ERROR"
        assert results["DisabledMod"] == "\u2718 OFF"
        # No mod should show the plain "✔ ON" fallback
        assert "\u2714 ON" not in results.values()

    def test_no_report_shows_on_off(self):
        """Before analysis (no report), enabled mods should show '✔ ON'."""
        profile = _make_profile([("ModA", True), ("ModB", False)])
        statuses = {}  # no report → empty dict

        results = {
            mod.name: self._status_column(mod, statuses)
            for mod in profile.mods
        }
        assert results["ModA"] == "\u2714 ON"
        assert results["ModB"] == "\u2718 OFF"

    def test_all_enabled_mods_covered_by_statuses(self):
        """compute_mod_statuses must return an entry for every enabled mod
        so the '✔ ON' fallback in _populate_mod_list is never reached."""
        profile = _make_profile([
            ("A", True), ("B", True), ("C", True), ("D", False),
        ])
        report = _empty_report(profile)
        statuses = compute_mod_statuses(report, profile.mods)

        for mod in profile.mods:
            if mod.enabled:
                assert mod.name in statuses, (
                    f"Enabled mod '{mod.name}' missing from statuses dict"
                )


# ---------------------------------------------------------------------------
# _version_is_older
# ---------------------------------------------------------------------------

class TestVersionIsOlder:
    def test_newer_semver(self):
        assert _version_is_older("1.0.0", "2.0.0") is True

    def test_same_version(self):
        assert _version_is_older("1.2.3", "1.2.3") is False

    def test_local_is_newer(self):
        assert _version_is_older("2.0.0", "1.0.0") is False

    def test_minor_bump(self):
        assert _version_is_older("1.0.0", "1.1.0") is True

    def test_patch_bump(self):
        assert _version_is_older("1.0.0", "1.0.1") is True

    def test_empty_local(self):
        assert _version_is_older("", "1.0.0") is False

    def test_empty_remote(self):
        assert _version_is_older("1.0.0", "") is False

    def test_placeholder_local(self):
        assert _version_is_older("?", "1.0.0") is False

    def test_non_numeric_mismatch(self):
        assert _version_is_older("1.0a", "1.0b") is False

    def test_non_numeric_same(self):
        assert _version_is_older("1.0a", "1.0a") is False


# ---------------------------------------------------------------------------
# compute_mod_statuses with version comparison
# ---------------------------------------------------------------------------

class TestComputeModStatusesVersionCheck:
    """Verify that compute_mod_statuses flags outdated mods as ⚠ UPDATE."""

    def test_outdated_mod_gets_update_status(self, db):
        db.upsert_mod({
            "mod_id": 100, "name": "SkyUI", "version": "5.5",
            "summary": "", "last_updated": "2024-01-01T00:00:00",
        })
        profile = _make_profile([("SkyUI", True)])
        # Give the mod a nexus_id and older version
        profile.mods[0].nexus_id = "100"
        profile.mods[0].version = "5.2"
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods, db=db)
        assert result["SkyUI"] == "\u26a0 UPDATE"

    def test_up_to_date_mod_stays_ok(self, db):
        db.upsert_mod({
            "mod_id": 101, "name": "SKSE64", "version": "2.2.3",
            "summary": "", "last_updated": "2024-01-01T00:00:00",
        })
        profile = _make_profile([("SKSE64", True)])
        profile.mods[0].nexus_id = "101"
        profile.mods[0].version = "2.2.3"
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods, db=db)
        assert result["SKSE64"] == "\u2714 OK"

    def test_error_takes_precedence_over_update(self, db):
        db.upsert_mod({
            "mod_id": 102, "name": "SkyUI", "version": "5.5",
            "summary": "", "last_updated": "2024-01-01T00:00:00",
        })
        profile = _make_profile([("SkyUI", True)])
        profile.mods[0].nexus_id = "102"
        profile.mods[0].version = "5.2"
        report = _empty_report(profile)
        report["missing_requirements"].append(
            {"mod_name": "SkyUI", "required_name": "SKSE64", "is_patch": False}
        )
        result = compute_mod_statuses(report, profile.mods, db=db)
        assert result["SkyUI"] == "\u2718 ERROR"

    def test_no_db_skips_version_check(self):
        profile = _make_profile([("SkyUI", True)])
        profile.mods[0].nexus_id = "100"
        profile.mods[0].version = "5.2"
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods, db=None)
        assert result["SkyUI"] == "\u2714 OK"

    def test_no_nexus_id_skips_version_check(self, db):
        db.upsert_mod({
            "mod_id": 103, "name": "LocalMod", "version": "1.0",
            "summary": "", "last_updated": "2024-01-01T00:00:00",
        })
        profile = _make_profile([("LocalMod", True)])
        # nexus_id defaults to "0"
        report = _empty_report(profile)
        result = compute_mod_statuses(report, profile.mods, db=db)
        assert result["LocalMod"] == "\u2714 OK"
