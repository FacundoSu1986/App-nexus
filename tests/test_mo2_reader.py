"""Tests for MO2Reader."""

import textwrap
from pathlib import Path

import pytest

from src.mo2.reader import MO2Reader, MO2Profile, InstalledMod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# modlist.txt parsing
# ---------------------------------------------------------------------------

class TestReadModlist:
    def test_enabled_mod(self, tmp_path):
        p = tmp_path / "modlist.txt"
        write_file(p, "+My Awesome Mod\n")
        mods = MO2Reader._read_modlist(p)
        assert len(mods) == 1
        assert mods[0].name == "My Awesome Mod"
        assert mods[0].enabled is True

    def test_disabled_mod(self, tmp_path):
        p = tmp_path / "modlist.txt"
        write_file(p, "-Old Mod\n")
        mods = MO2Reader._read_modlist(p)
        assert mods[0].enabled is False
        assert mods[0].name == "Old Mod"

    def test_separator_lines_skipped(self, tmp_path):
        p = tmp_path / "modlist.txt"
        write_file(p, "*Separator\n+Real Mod\n")
        mods = MO2Reader._read_modlist(p)
        assert len(mods) == 1
        assert mods[0].name == "Real Mod"

    def test_comments_skipped(self, tmp_path):
        p = tmp_path / "modlist.txt"
        write_file(p, "# This is a comment\n+Valid Mod\n")
        mods = MO2Reader._read_modlist(p)
        assert len(mods) == 1

    def test_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "modlist.txt"
        write_file(p, "\n+Mod One\n\n+Mod Two\n")
        mods = MO2Reader._read_modlist(p)
        assert len(mods) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        mods = MO2Reader._read_modlist(tmp_path / "nonexistent.txt")
        assert mods == []


# ---------------------------------------------------------------------------
# plugins.txt parsing
# ---------------------------------------------------------------------------

class TestReadPlugins:
    def test_active_plugin_prefixed(self, tmp_path):
        p = tmp_path / "plugins.txt"
        write_file(p, "*Skyrim.esm\n*Update.esm\n")
        plugins = MO2Reader._read_plugins(p)
        assert plugins == ["Skyrim.esm", "Update.esm"]

    def test_inactive_plugin_no_prefix(self, tmp_path):
        p = tmp_path / "plugins.txt"
        write_file(p, "SomeMod.esp\n")
        plugins = MO2Reader._read_plugins(p)
        assert plugins == ["SomeMod.esp"]

    def test_order_preserved(self, tmp_path):
        p = tmp_path / "plugins.txt"
        write_file(p, "*A.esm\n*B.esp\n*C.esp\n")
        plugins = MO2Reader._read_plugins(p)
        assert plugins == ["A.esm", "B.esp", "C.esp"]

    def test_missing_file_returns_empty(self, tmp_path):
        plugins = MO2Reader._read_plugins(Path("/nonexistent/plugins.txt"))
        assert plugins == []


# ---------------------------------------------------------------------------
# from_files() convenience constructor
# ---------------------------------------------------------------------------

class TestFromFiles:
    def test_from_files_basic(self, tmp_path):
        modlist = tmp_path / "modlist.txt"
        plugins = tmp_path / "plugins.txt"
        write_file(modlist, "+ModA\n+ModB\n-ModC\n")
        write_file(plugins, "*ModA.esp\n*ModB.esp\n")

        profile = MO2Reader.from_files(str(modlist), str(plugins), "TestProfile")
        assert profile.profile_name == "TestProfile"
        assert len(profile.mods) == 3
        assert len(profile.enabled_mods) == 2
        assert profile.load_order == ["ModA.esp", "ModB.esp"]

    def test_from_files_no_plugins(self, tmp_path):
        modlist = tmp_path / "modlist.txt"
        write_file(modlist, "+OnlyMod\n")
        profile = MO2Reader.from_files(str(modlist))
        assert profile.load_order == []


# ---------------------------------------------------------------------------
# MO2Profile helpers
# ---------------------------------------------------------------------------

class TestMO2Profile:
    def _make_profile(self):
        return MO2Profile(
            profile_name="Default",
            mods=[
                InstalledMod(name="Alpha", enabled=True),
                InstalledMod(name="Beta", enabled=False),
                InstalledMod(name="Gamma", enabled=True),
            ],
        )

    def test_enabled_mods(self):
        p = self._make_profile()
        assert len(p.enabled_mods) == 2

    def test_enabled_mod_names(self):
        p = self._make_profile()
        assert "Alpha" in p.enabled_mod_names
        assert "Beta" not in p.enabled_mod_names


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

class TestNormaliseName:
    def test_strips_version_suffix(self):
        assert MO2Reader.normalise_name("SKSE64 - 2.2.3") == "skse64"

    def test_strips_underscore_version(self):
        assert MO2Reader.normalise_name("SomePlugin_v1.5") == "someplugin"

    def test_already_clean(self):
        assert MO2Reader.normalise_name("Unofficial Skyrim Patch") == "unofficial skyrim patch"

    def test_extra_spaces_collapsed(self):
        # The function collapses multiple spaces into one.
        assert MO2Reader.normalise_name("Mod  With  Spaces") == "mod with spaces"


# ---------------------------------------------------------------------------
# _read_meta_ini
# ---------------------------------------------------------------------------

class TestReadMetaIni:
    def test_reads_modid_and_version(self, tmp_path):
        mod_dir = tmp_path / "mods" / "SkyUI"
        mod_dir.mkdir(parents=True)
        (mod_dir / "meta.ini").write_text(
            "[General]\nmodid=3863\nversion=5.2\n", encoding="utf-8"
        )
        result = MO2Reader._read_meta_ini(tmp_path / "mods", "SkyUI")
        assert result["nexus_id"] == "3863"
        assert result["version"] == "5.2"

    def test_missing_meta_ini_returns_defaults(self, tmp_path):
        result = MO2Reader._read_meta_ini(tmp_path / "mods", "NoSuchMod")
        assert result["nexus_id"] == "0"
        assert result["version"] == "?"

    def test_missing_general_section_returns_defaults(self, tmp_path):
        mod_dir = tmp_path / "mods" / "WeirdMod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "meta.ini").write_text(
            "[SomeOtherSection]\nfoo=bar\n", encoding="utf-8"
        )
        result = MO2Reader._read_meta_ini(tmp_path / "mods", "WeirdMod")
        assert result["nexus_id"] == "0"
        assert result["version"] == "?"

    def test_missing_keys_returns_defaults(self, tmp_path):
        mod_dir = tmp_path / "mods" / "PartialMod"
        mod_dir.mkdir(parents=True)
        (mod_dir / "meta.ini").write_text(
            "[General]\nauthor=Someone\n", encoding="utf-8"
        )
        result = MO2Reader._read_meta_ini(tmp_path / "mods", "PartialMod")
        assert result["nexus_id"] == "0"
        assert result["version"] == "?"


# ---------------------------------------------------------------------------
# _read_modlist with meta.ini integration
# ---------------------------------------------------------------------------

class TestReadModlistWithMetaIni:
    def _setup_mo2(self, tmp_path, mods_meta: dict):
        """Create an MO2-like directory structure.

        ``mods_meta`` maps mod name → dict with optional modid/version.
        Returns path to modlist.txt.
        """
        profile_dir = tmp_path / "profiles" / "Default"
        profile_dir.mkdir(parents=True)
        mods_dir = tmp_path / "mods"
        mods_dir.mkdir(exist_ok=True)

        lines = []
        for name, meta in mods_meta.items():
            lines.append(f"+{name}")
            mod_dir = mods_dir / name
            mod_dir.mkdir(exist_ok=True)
            ini_lines = ["[General]"]
            if "modid" in meta:
                ini_lines.append(f"modid={meta['modid']}")
            if "version" in meta:
                ini_lines.append(f"version={meta['version']}")
            (mod_dir / "meta.ini").write_text(
                "\n".join(ini_lines) + "\n", encoding="utf-8"
            )

        modlist_path = profile_dir / "modlist.txt"
        modlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return modlist_path

    def test_populates_nexus_id_and_version(self, tmp_path):
        modlist = self._setup_mo2(tmp_path, {
            "SkyUI": {"modid": "3863", "version": "5.2"},
            "SKSE64": {"modid": "30379", "version": "2.2.3"},
        })
        mods = MO2Reader._read_modlist(modlist)
        assert len(mods) == 2
        sky = next(m for m in mods if m.name == "SkyUI")
        assert sky.nexus_id == "3863"
        assert sky.version == "5.2"
        skse = next(m for m in mods if m.name == "SKSE64")
        assert skse.nexus_id == "30379"
        assert skse.version == "2.2.3"

    def test_mod_without_meta_ini_gets_defaults(self, tmp_path):
        profile_dir = tmp_path / "profiles" / "Default"
        profile_dir.mkdir(parents=True)
        (tmp_path / "mods").mkdir(exist_ok=True)
        modlist = profile_dir / "modlist.txt"
        modlist.write_text("+NoMetaMod\n", encoding="utf-8")
        mods = MO2Reader._read_modlist(modlist)
        assert mods[0].nexus_id == "0"
        assert mods[0].version == "?"


# ---------------------------------------------------------------------------
# Instance / profile discovery (with mocked filesystem)
# ---------------------------------------------------------------------------

class TestInstanceDiscovery:
    def test_list_instances(self, tmp_path):
        (tmp_path / "SkyrimSE").mkdir()
        (tmp_path / "Fallout4").mkdir()
        reader = MO2Reader(instance_root=tmp_path)
        instances = reader.list_instances()
        assert "SkyrimSE" in instances
        assert "Fallout4" in instances

    def test_list_profiles(self, tmp_path):
        profile_dir = tmp_path / "SkyrimSE" / "profiles"
        (profile_dir / "Default").mkdir(parents=True)
        (profile_dir / "Hardcore").mkdir(parents=True)
        reader = MO2Reader(instance_root=tmp_path)
        profiles = reader.list_profiles("SkyrimSE")
        assert "Default" in profiles
        assert "Hardcore" in profiles

    def test_read_profile(self, tmp_path):
        profile_dir = tmp_path / "SkyrimSE" / "profiles" / "Default"
        profile_dir.mkdir(parents=True)
        write_file(profile_dir / "modlist.txt", "+SKSE64\n+SkyUI\n")
        write_file(profile_dir / "plugins.txt", "*SKSE64.esm\n")
        reader = MO2Reader(instance_root=tmp_path)
        profile = reader.read_profile("SkyrimSE", "Default")
        assert profile.profile_name == "Default"
        assert len(profile.mods) == 2
        assert profile.load_order == ["SKSE64.esm"]
