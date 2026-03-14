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
            "last_updated": "2024-01-01T00:00:00",
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
