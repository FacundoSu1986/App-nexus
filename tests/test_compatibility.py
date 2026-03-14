"""Tests for CompatibilityAnalyzer."""

import pytest

from src.analyzer.compatibility import CompatibilityAnalyzer, _similar, _mod_in_list
from src.database.manager import DatabaseManager
from src.mo2.reader import MO2Profile, InstalledMod


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

class TestSimilar:
    def test_exact_match(self):
        assert _similar("SKSE64", "SKSE64") is True

    def test_case_insensitive(self):
        assert _similar("skyui", "SkyUI") is True

    def test_high_similarity(self):
        assert _similar("Unofficial Skyrim Patch", "Unofficial Skyrim Special Edition Patch") is False

    def test_very_different(self):
        assert _similar("ModA", "Completely Different Mod") is False


class TestModInList:
    def test_found_exact(self):
        assert _mod_in_list("SkyUI", ["SKSE64", "SkyUI", "USSEP"]) is True

    def test_not_found(self):
        assert _mod_in_list("MissingMod", ["SKSE64", "SkyUI"]) is False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_path=str(tmp_path / "test.db"))
    manager.connect()
    yield manager
    manager.close()


def _make_profile(mod_names: list, load_order: list = None) -> MO2Profile:
    mods = [InstalledMod(name=n, enabled=True) for n in mod_names]
    return MO2Profile(
        profile_name="Test",
        mods=mods,
        load_order=load_order or [],
    )


def _seed_mod(db: DatabaseManager, mod_id: int, name: str) -> None:
    db.upsert_mod(
        {
            "mod_id": mod_id,
            "name": name,
            "summary": "",
            "last_scraped": "2024-01-01T00:00:00",
        }
    )


# ---------------------------------------------------------------------------
# Missing requirements
# ---------------------------------------------------------------------------

class TestMissingRequirements:
    def test_detects_missing_required_mod(self, db):
        _seed_mod(db, 1, "SkyUI")
        db.upsert_requirements(
            1, [{"required_name": "SKSE64", "is_patch": False, "required_url": ""}]
        )
        profile = _make_profile(["SkyUI"])  # SKSE64 NOT installed
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        missing_names = [m["required_name"] for m in report["missing_requirements"]]
        assert "SKSE64" in missing_names

    def test_no_false_positive_when_present(self, db):
        _seed_mod(db, 2, "SkyUI")
        db.upsert_requirements(
            2, [{"required_name": "SKSE64", "is_patch": False, "required_url": ""}]
        )
        profile = _make_profile(["SkyUI", "SKSE64"])  # both installed
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["missing_requirements"] == []

    def test_identifies_missing_patch(self, db):
        _seed_mod(db, 3, "ModA")
        db.upsert_requirements(
            3,
            [
                {
                    "required_name": "ModA-ModB Patch",
                    "is_patch": True,
                    "required_url": "",
                }
            ],
        )
        profile = _make_profile(["ModA"])
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["stats"]["missing_patches"] == 1
        assert report["missing_requirements"][0]["is_patch"] is True


# ---------------------------------------------------------------------------
# Incompatibilities
# ---------------------------------------------------------------------------

class TestIncompatibilities:
    def test_detects_conflict(self, db):
        _seed_mod(db, 10, "ModA")
        db.upsert_incompatibilities(
            10, [{"incompatible_name": "ModB", "reason": "Overwrites same records"}]
        )
        profile = _make_profile(["ModA", "ModB"])  # both installed → conflict!
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert len(report["incompatibilities"]) == 1
        assert report["incompatibilities"][0]["incompatible_name"] == "ModB"

    def test_no_conflict_when_absent(self, db):
        _seed_mod(db, 11, "ModA")
        db.upsert_incompatibilities(
            11, [{"incompatible_name": "Completely Different Mod", "reason": "Conflict"}]
        )
        profile = _make_profile(["ModA"])  # "Completely Different Mod" not installed
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["incompatibilities"] == []


# ---------------------------------------------------------------------------
# Load-order rules
# ---------------------------------------------------------------------------

class TestLoadOrderViolations:
    def test_detects_after_violation(self):
        rule = {"rule_type": "AFTER", "target_mod_name": "USSEP.esp"}
        load_order = ["SkyUI.esp", "USSEP.esp"]  # SkyUI is BEFORE USSEP → violation
        result = CompatibilityAnalyzer._check_load_order_rule(
            "SkyUI.esp", rule, load_order
        )
        assert result is not None
        assert result["rule_type"] == "AFTER"

    def test_no_violation_when_correct(self):
        rule = {"rule_type": "AFTER", "target_mod_name": "USSEP.esp"}
        load_order = ["USSEP.esp", "SkyUI.esp"]  # SkyUI AFTER USSEP → OK
        result = CompatibilityAnalyzer._check_load_order_rule(
            "SkyUI.esp", rule, load_order
        )
        assert result is None

    def test_detects_before_violation(self):
        rule = {"rule_type": "BEFORE", "target_mod_name": "USSEP.esp"}
        load_order = ["USSEP.esp", "SkyUI.esp"]  # SkyUI should be BEFORE USSEP but isn't
        result = CompatibilityAnalyzer._check_load_order_rule(
            "SkyUI.esp", rule, load_order
        )
        assert result is not None

    def test_returns_none_when_plugin_not_in_load_order(self):
        rule = {"rule_type": "AFTER", "target_mod_name": "Missing.esp"}
        result = CompatibilityAnalyzer._check_load_order_rule(
            "SomeMod.esp", rule, ["SomeMod.esp"]
        )
        assert result is None

    def test_full_analysis_with_rules(self, db):
        _seed_mod(db, 20, "SkyUI")
        db.upsert_load_order_rules(
            20,
            [{"rule_type": "AFTER", "target_mod_name": "USSEP.esp", "notes": ""}],
        )
        # SkyUI (and its plugin SkyUI.esp) appears BEFORE USSEP.esp → violation
        # Profile load_order uses plugin names; SkyUI.esp matches mod name "SkyUI"
        # because _similar strips the .esp extension before comparing.
        profile = _make_profile(["SkyUI"], load_order=["SkyUI.esp", "USSEP.esp"])
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["stats"]["violations_count"] == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_summary(self, db):
        _seed_mod(db, 30, "ModX")
        profile = MO2Profile(
            profile_name="T",
            mods=[
                InstalledMod("ModX", enabled=True),
                InstalledMod("DisabledMod", enabled=False),
            ],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["stats"]["total_mods"] == 2
        assert report["stats"]["enabled_mods"] == 1
