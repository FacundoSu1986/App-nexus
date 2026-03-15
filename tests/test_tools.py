"""Tests for AI function-calling tools."""

import json

import pytest
from unittest.mock import MagicMock

from src.ai.tools import (
    OLLAMA_TOOLS,
    ANTHROPIC_TOOLS,
    CHAT_SYSTEM_PROMPT,
    ToolExecutor,
)


class TestToolDefinitions:
    """Validate tool schema structure."""

    def test_ollama_tools_has_four_tools(self):
        assert len(OLLAMA_TOOLS) == 5

    def test_anthropic_tools_has_four_tools(self):
        assert len(ANTHROPIC_TOOLS) == 5

    def test_ollama_tool_names(self):
        names = [t["function"]["name"] for t in OLLAMA_TOOLS]
        assert "search_mod" in names
        assert "get_mod_requirements" in names
        assert "get_loot_warnings" in names
        assert "find_patches" in names
        assert "get_mod_description" in names

    def test_anthropic_tool_names(self):
        names = [t["name"] for t in ANTHROPIC_TOOLS]
        assert "search_mod" in names
        assert "get_mod_requirements" in names
        assert "get_loot_warnings" in names
        assert "find_patches" in names
        assert "get_mod_description" in names

    def test_ollama_tools_have_required_fields(self):
        for tool in OLLAMA_TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"
            assert "required" in func["parameters"]

    def test_anthropic_tools_have_required_fields(self):
        for tool in ANTHROPIC_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "required" in tool["input_schema"]

    def test_chat_system_prompt_is_nonempty(self):
        assert len(CHAT_SYSTEM_PROMPT) > 50
        assert "Skyrim" in CHAT_SYSTEM_PROMPT


class TestToolExecutor:
    """Test the ToolExecutor against a mock DatabaseManager."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.search_mods_by_name.return_value = [
            {
                "mod_id": 100,
                "name": "Immersive Weapons",
                "version": "1.0",
                "author": "Author",
                "mod_url": "https://nexusmods.com/skyrimspecialedition/mods/100",
            }
        ]
        db.get_requirements.return_value = [
            {
                "required_name": "SKSE64",
                "is_patch": 0,
                "required_url": "https://example.com",
            },
            {
                "required_name": "IW USSEP Patch",
                "is_patch": 1,
                "required_url": "",
            },
        ]
        db.get_loot_entry.return_value = {
            "name": "SkyUI_SE.esp",
            "req": ["SKSE64"],
            "inc": [],
            "msg": ["[warn] Requires SKSE 2.0+"],
        }
        db.search_loot_entries_by_name.return_value = []
        return db

    def test_search_mod(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("search_mod", {"name": "Immersive"})
        result = json.loads(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Immersive Weapons"
        assert result[0]["mod_id"] == 100
        mock_db.search_mods_by_name.assert_called_once_with("Immersive")

    def test_get_mod_requirements(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_mod_requirements", {"nexus_id": "100"})
        result = json.loads(raw)
        assert len(result) == 2
        assert result[0]["required_name"] == "SKSE64"
        assert result[1]["is_patch"] is True
        mock_db.get_requirements.assert_called_once_with(100)

    def test_get_mod_requirements_invalid_id(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_mod_requirements", {"nexus_id": "abc"})
        result = json.loads(raw)
        assert len(result) == 1
        assert "error" in result[0]

    def test_get_loot_warnings(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_loot_warnings", {"plugin_name": "SkyUI_SE.esp"})
        result = json.loads(raw)
        assert result["plugin"] == "SkyUI_SE.esp"
        assert "SKSE64" in result["requirements"]
        assert len(result["messages"]) == 1
        mock_db.get_loot_entry.assert_called_once_with("SkyUI_SE.esp")

    def test_get_loot_warnings_not_found(self, mock_db):
        mock_db.get_loot_entry.return_value = None
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_loot_warnings", {"plugin_name": "Unknown.esp"})
        result = json.loads(raw)
        assert "No LOOT data found" in result.get("note", "")

    def test_find_patches(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("find_patches", {"mod_name": "Immersive Weapons"})
        result = json.loads(raw)
        patch_names = [p["patch_name"] for p in result]
        assert "IW USSEP Patch" in patch_names

    def test_unknown_tool(self, mock_db):
        executor = ToolExecutor(mock_db)
        raw = executor.execute("nonexistent_tool", {})
        result = json.loads(raw)
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_tool_exception_returns_error(self, mock_db):
        mock_db.search_mods_by_name.side_effect = RuntimeError("DB error")
        executor = ToolExecutor(mock_db)
        raw = executor.execute("search_mod", {"name": "test"})
        result = json.loads(raw)
        assert "error" in result
        assert "DB error" in result["error"]

    def test_get_mod_description_found(self, mock_db):
        mock_db.get_ai_analysis.return_value = {
            "nexus_id": "100",
            "requirements": ["SKSE64"],
            "patches": ["Patch A"],
            "known_issues": ["Bug X"],
            "load_order": ["Load after USSEP"],
            "analyzed_by": "ollama",
            "last_analyzed": "2024-06-01T12:00:00Z",
        }
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_mod_description", {"nexus_id": "100"})
        result = json.loads(raw)
        assert result["nexus_id"] == "100"
        assert result["requirements"] == ["SKSE64"]
        assert result["load_order"] == ["Load after USSEP"]
        mock_db.get_ai_analysis.assert_called_once_with("100")

    def test_get_mod_description_not_found(self, mock_db):
        mock_db.get_ai_analysis.return_value = None
        executor = ToolExecutor(mock_db)
        raw = executor.execute("get_mod_description", {"nexus_id": "99999"})
        result = json.loads(raw)
        assert "No AI analysis cached" in result.get("note", "")
