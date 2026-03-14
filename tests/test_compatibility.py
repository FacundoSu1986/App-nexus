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
# LOOT lookups via load_order
# ---------------------------------------------------------------------------

class TestLootLookup:
    def test_loot_uses_load_order_for_lookups(self, db):
        """LOOT entries are keyed by plugin filename; the analyzer should use
        profile.load_order (plugin filenames) not mod.name for lookups."""
        import json
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            ("SkyUI_SE.esp", "[]", json.dumps(["Conflict.esp"]), "[]"),
        )
        db.conn.commit()
        profile = MO2Profile(
            profile_name="T",
            mods=[InstalledMod("SkyUI", enabled=True)],
            load_order=["SkyUI_SE.esp", "Conflict.esp"],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert len(report["loot_incompatibilities"]) == 1
        assert report["loot_incompatibilities"][0]["mod_name"] == "SkyUI_SE.esp"

    def test_loot_warnings_from_load_order(self, db):
        import json
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            ("USSEP.esp", "[]", "[]", json.dumps(["[warn] Needs update"])),
        )
        db.conn.commit()
        profile = MO2Profile(
            profile_name="T",
            mods=[InstalledMod("USSEP", enabled=True)],
            load_order=["USSEP.esp"],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert len(report["loot_warnings"]) == 1
        assert report["loot_warnings"][0]["mod_name"] == "USSEP.esp"

    def test_mod_folder_name_does_not_match_loot_plugin(self, db):
        """Regression: mod folder names (e.g. 'Immersive Armors') must NOT
        match LOOT entries keyed by plugin filename
        (e.g. 'Hothtrooper44_ArmorCompilation.esp').  LOOT lookups must use
        the load_order list exclusively."""
        import json
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            (
                "Hothtrooper44_ArmorCompilation.esp",
                "[]",
                json.dumps(["SomeConflict.esp"]),
                json.dumps(["[warn] check load order"]),
            ),
        )
        db.conn.commit()

        # Plugin is NOT in load_order, so LOOT data must be ignored even
        # though the mod folder name is present in enabled_mods.
        profile = MO2Profile(
            profile_name="T",
            mods=[InstalledMod("Immersive Armors", enabled=True)],
            load_order=[],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["loot_incompatibilities"] == []
        assert report["loot_warnings"] == []

    def test_loot_found_only_when_plugin_in_load_order(self, db):
        """LOOT incompatibilities surface only when the plugin filename
        appears in profile.load_order, not because a similarly-named mod
        folder exists."""
        import json
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            (
                "Hothtrooper44_ArmorCompilation.esp",
                "[]",
                json.dumps(["SomeConflict.esp"]),
                json.dumps(["[warn] check load order"]),
            ),
        )
        db.conn.commit()

        # Now put the plugin in load_order together with its conflict.
        profile = MO2Profile(
            profile_name="T",
            mods=[InstalledMod("Immersive Armors", enabled=True)],
            load_order=[
                "Hothtrooper44_ArmorCompilation.esp",
                "SomeConflict.esp",
            ],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert len(report["loot_incompatibilities"]) == 1
        assert (
            report["loot_incompatibilities"][0]["mod_name"]
            == "Hothtrooper44_ArmorCompilation.esp"
        )
        assert len(report["loot_warnings"]) == 1

    def test_loot_conflict_not_in_load_order_is_ignored(self, db):
        """If the conflicting plugin from LOOT is not in load_order the
        incompatibility should NOT be reported."""
        import json
        db.conn.execute(
            "INSERT INTO loot_entries (name, req, inc, msg) VALUES (?, ?, ?, ?)",
            (
                "Hothtrooper44_ArmorCompilation.esp",
                "[]",
                json.dumps(["SomeConflict.esp"]),
                "[]",
            ),
        )
        db.conn.commit()

        # Plugin present but the conflicting plugin is NOT installed.
        profile = MO2Profile(
            profile_name="T",
            mods=[InstalledMod("Immersive Armors", enabled=True)],
            load_order=["Hothtrooper44_ArmorCompilation.esp"],
        )
        analyzer = CompatibilityAnalyzer(db)
        report = analyzer.analyse(profile)
        assert report["loot_incompatibilities"] == []


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
