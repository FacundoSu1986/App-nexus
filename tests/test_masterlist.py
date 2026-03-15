"""Tests for the LOOT masterlist parser."""

import pytest

from src.database.manager import DatabaseManager
from src.loot.masterlist import (
    MASTERLIST_URL,
    parse_masterlist,
    save_to_database,
    clean_loot_message,
    _extract_requirements,
    _extract_incompatibilities,
    _extract_messages,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_path=str(tmp_path / "test.db"))
    manager.connect()
    yield manager
    manager.close()


SAMPLE_YAML = """\
plugins:
  - name: SkyUI_SE.esp
    req:
      - SKSE64_Loader.exe
    inc:
      - OldConflict.esp
    msg:
      - type: warn
        content: "Requires SKSE64 to function properly."
  - name: USSEP.esp
    req:
      - name: Skyrim.esm
    inc:
      - LegacyPatch.esp
      - name: AnotherConflict.esp
    msg:
      - "Simple text message"
  - name: EmptyPlugin.esp
"""


# ---------------------------------------------------------------------------
# parse_masterlist
# ---------------------------------------------------------------------------

class TestMasterlistUrl:
    def test_url_uses_v0_17_tag(self):
        assert "loot/skyrimse/v0.17/" in MASTERLIST_URL

    def test_url_points_to_masterlist_yaml(self):
        assert MASTERLIST_URL.endswith("masterlist.yaml")


class TestParseMasterlist:
    def test_parses_all_plugins(self):
        entries = parse_masterlist(SAMPLE_YAML)
        names = [e["name"] for e in entries]
        assert "SkyUI_SE.esp" in names
        assert "USSEP.esp" in names
        assert "EmptyPlugin.esp" in names

    def test_extracts_requirements_strings(self):
        entries = parse_masterlist(SAMPLE_YAML)
        skyui = next(e for e in entries if e["name"] == "SkyUI_SE.esp")
        assert "SKSE64_Loader.exe" in skyui["req"]

    def test_extracts_requirements_dicts(self):
        entries = parse_masterlist(SAMPLE_YAML)
        ussep = next(e for e in entries if e["name"] == "USSEP.esp")
        assert "Skyrim.esm" in ussep["req"]

    def test_extracts_incompatibilities_strings(self):
        entries = parse_masterlist(SAMPLE_YAML)
        skyui = next(e for e in entries if e["name"] == "SkyUI_SE.esp")
        assert "OldConflict.esp" in skyui["inc"]

    def test_extracts_incompatibilities_dicts(self):
        entries = parse_masterlist(SAMPLE_YAML)
        ussep = next(e for e in entries if e["name"] == "USSEP.esp")
        assert "AnotherConflict.esp" in ussep["inc"]
        assert "LegacyPatch.esp" in ussep["inc"]

    def test_extracts_messages_dict_form(self):
        entries = parse_masterlist(SAMPLE_YAML)
        skyui = next(e for e in entries if e["name"] == "SkyUI_SE.esp")
        assert len(skyui["msg"]) == 1
        assert "Requires SKSE64" in skyui["msg"][0]

    def test_extracts_messages_string_form(self):
        entries = parse_masterlist(SAMPLE_YAML)
        ussep = next(e for e in entries if e["name"] == "USSEP.esp")
        assert "Simple text message" in ussep["msg"]

    def test_empty_plugin_defaults(self):
        entries = parse_masterlist(SAMPLE_YAML)
        empty = next(e for e in entries if e["name"] == "EmptyPlugin.esp")
        assert empty["req"] == []
        assert empty["inc"] == []
        assert empty["msg"] == []

    def test_invalid_yaml_returns_empty(self):
        assert parse_masterlist("not_a_dict: [") == []

    def test_missing_plugins_key_returns_empty(self):
        assert parse_masterlist("globals:\n  key: val") == []

    def test_plugins_not_list_returns_empty(self):
        assert parse_masterlist("plugins: not_a_list") == []


# ---------------------------------------------------------------------------
# extract helpers
# ---------------------------------------------------------------------------

class TestExtractRequirements:
    def test_string_items(self):
        assert _extract_requirements({"req": ["A.esp", "B.esp"]}) == ["A.esp", "B.esp"]

    def test_dict_items(self):
        assert _extract_requirements({"req": [{"name": "C.esp"}]}) == ["C.esp"]

    def test_empty(self):
        assert _extract_requirements({}) == []

    def test_non_list_returns_empty(self):
        assert _extract_requirements({"req": "single_string"}) == []


class TestExtractIncompatibilities:
    def test_string_items(self):
        assert _extract_incompatibilities({"inc": ["X.esp"]}) == ["X.esp"]

    def test_dict_items(self):
        assert _extract_incompatibilities({"inc": [{"name": "Y.esp"}]}) == ["Y.esp"]

    def test_empty(self):
        assert _extract_incompatibilities({}) == []

    def test_non_list_returns_empty(self):
        assert _extract_incompatibilities({"inc": "single_string"}) == []


class TestExtractMessages:
    def test_dict_with_content(self):
        msgs = _extract_messages({"msg": [{"type": "warn", "content": "hello"}]})
        assert len(msgs) == 1
        assert "[warn]" in msgs[0]
        assert "hello" in msgs[0]

    def test_string_message(self):
        msgs = _extract_messages({"msg": ["plain text"]})
        assert msgs == ["plain text"]

    def test_empty(self):
        assert _extract_messages({}) == []

    def test_non_list_returns_empty(self):
        assert _extract_messages({"msg": "single_string"}) == []


class TestCleanLootMessage:
    def test_single_placeholder_replaced(self):
        assert clean_loot_message("Contains %1% ITM records.") == \
            "Contains [see Nexus page] ITM records."

    def test_multiple_placeholders_replaced(self):
        result = clean_loot_message("Use %1% to clean %2% records.")
        assert "%1%" not in result
        assert "%2%" not in result
        assert result == "Use [see Nexus page] to clean [see Nexus page] records."

    def test_no_placeholder_unchanged(self):
        assert clean_loot_message("No placeholders here.") == "No placeholders here."

    def test_empty_string(self):
        assert clean_loot_message("") == ""

    def test_only_placeholder(self):
        assert clean_loot_message("%1%") == "[see Nexus page]"

    def test_adjacent_placeholders_no_double_space(self):
        result = clean_loot_message("%1% %2%")
        assert result == "[see Nexus page] [see Nexus page]"

    def test_extract_messages_cleans_placeholders(self):
        """Verify _extract_messages applies cleaning."""
        plugin = {"msg": ["Contains %1% ITM records."]}
        msgs = _extract_messages(plugin)
        assert "%1%" not in msgs[0]
        assert "[see Nexus page]" in msgs[0]

    def test_extract_messages_cleans_dict_form(self):
        plugin = {"msg": [{"type": "warn", "content": "Needs %1%"}]}
        msgs = _extract_messages(plugin)
        assert "%1%" not in msgs[0]
        assert "[see Nexus page]" in msgs[0]


# ---------------------------------------------------------------------------
# save_to_database
# ---------------------------------------------------------------------------

class TestSaveToDatabase:
    def test_saves_and_retrieves(self, db):
        entries = parse_masterlist(SAMPLE_YAML)
        count = save_to_database(entries, db)
        assert count == 3

        entry = db.get_loot_entry("SkyUI_SE.esp")
        assert entry is not None
        assert "SKSE64_Loader.exe" in entry["req"]
        assert "OldConflict.esp" in entry["inc"]

    def test_upsert_replaces_existing(self, db):
        save_to_database([{"name": "A.esp", "req": ["B.esp"], "inc": [], "msg": []}], db)
        save_to_database([{"name": "A.esp", "req": ["C.esp"], "inc": [], "msg": []}], db)
        entry = db.get_loot_entry("A.esp")
        assert entry["req"] == ["C.esp"]
