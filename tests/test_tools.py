"""Tests for AI function-calling tools."""

import json
import subprocess

import pytest
from unittest.mock import MagicMock, patch

from src.ai.tools import (
    OLLAMA_TOOLS,
    ANTHROPIC_TOOLS,
    CHAT_SYSTEM_PROMPT,
    ToolExecutor,
    execute_download_and_install,
    execute_shell,
)


class TestToolDefinitions:
    """Validate tool schema structure."""

    def test_ollama_tools_has_six_tools(self):
        assert len(OLLAMA_TOOLS) == 6

    def test_anthropic_tools_has_six_tools(self):
        assert len(ANTHROPIC_TOOLS) == 6

    def test_ollama_tool_names(self):
        names = [t["function"]["name"] for t in OLLAMA_TOOLS]
        assert "search_mod" in names
        assert "get_mod_requirements" in names
        assert "get_loot_warnings" in names
        assert "find_patches" in names
        assert "download_and_install_mod" in names
        assert "execute_shell_command" in names

    def test_anthropic_tool_names(self):
        names = [t["name"] for t in ANTHROPIC_TOOLS]
        assert "search_mod" in names
        assert "get_mod_requirements" in names
        assert "get_loot_warnings" in names
        assert "find_patches" in names
        assert "download_and_install_mod" in names
        assert "execute_shell_command" in names

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

    def test_download_and_install_mod_schema_ollama(self):
        tool = next(
            t for t in OLLAMA_TOOLS
            if t["function"]["name"] == "download_and_install_mod"
        )
        params = tool["function"]["parameters"]
        assert set(params["required"]) == {"nexus_id", "file_id", "mod_name"}
        assert "nexus_id" in params["properties"]
        assert "file_id" in params["properties"]
        assert "mod_name" in params["properties"]

    def test_download_and_install_mod_schema_anthropic(self):
        tool = next(
            t for t in ANTHROPIC_TOOLS
            if t["name"] == "download_and_install_mod"
        )
        schema = tool["input_schema"]
        assert set(schema["required"]) == {"nexus_id", "file_id", "mod_name"}
        assert "nexus_id" in schema["properties"]
        assert "file_id" in schema["properties"]
        assert "mod_name" in schema["properties"]


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


class TestDownloadAndInstallMod:
    """Test the download_and_install_mod tool."""

    ARGS = {"nexus_id": "1234", "file_id": "5678", "mod_name": "TestMod"}

    @patch("src.ai.tools.install_mod")
    @patch("src.ai.tools.download_mod_file")
    @patch("os.makedirs")
    def test_success(self, mock_makedirs, mock_download, mock_install, monkeypatch):
        monkeypatch.setenv("MO2_BASE_PATH", "/fake/mo2")
        mock_download.return_value = "/tmp/downloads/testmod.7z"
        mock_install.return_value = True

        result = execute_download_and_install(self.ARGS)

        assert result.startswith("Success:")
        assert "TestMod" in result
        mock_download.assert_called_once()
        mock_install.assert_called_once()

    @patch("src.ai.tools.install_mod")
    @patch("src.ai.tools.download_mod_file")
    @patch("os.makedirs")
    def test_download_failure(self, mock_makedirs, mock_download, mock_install, monkeypatch):
        monkeypatch.setenv("MO2_BASE_PATH", "/fake/mo2")
        mock_download.return_value = None

        result = execute_download_and_install(self.ARGS)

        assert result == "Error: Failed to download mod from Nexus."
        mock_install.assert_not_called()

    @patch("src.ai.tools.install_mod")
    @patch("src.ai.tools.download_mod_file")
    @patch("os.makedirs")
    def test_install_failure(self, mock_makedirs, mock_download, mock_install, monkeypatch):
        monkeypatch.setenv("MO2_BASE_PATH", "/fake/mo2")
        mock_download.return_value = "/tmp/downloads/testmod.7z"
        mock_install.return_value = False

        result = execute_download_and_install(self.ARGS)

        assert result == "Error: Failed to extract and install mod."

    @patch("src.ai.tools.download_mod_file")
    @patch("os.makedirs")
    def test_exception_returns_error_string(self, mock_makedirs, mock_download, monkeypatch):
        monkeypatch.setenv("MO2_BASE_PATH", "/fake/mo2")
        mock_download.side_effect = RuntimeError("Network timeout")

        result = execute_download_and_install(self.ARGS)

        assert result.startswith("Error:")
        assert "Network timeout" in result

    def test_missing_mo2_base_path(self, monkeypatch):
        monkeypatch.delenv("MO2_BASE_PATH", raising=False)

        result = execute_download_and_install(self.ARGS)

        assert result == "Error: MO2_BASE_PATH is not configured."

    @patch("src.ai.tools.install_mod")
    @patch("src.ai.tools.download_mod_file")
    @patch("os.makedirs")
    def test_via_tool_executor(self, mock_makedirs, mock_download, mock_install, monkeypatch):
        monkeypatch.setenv("MO2_BASE_PATH", "/fake/mo2")
        mock_download.return_value = "/tmp/downloads/testmod.7z"
        mock_install.return_value = True
        mock_db = MagicMock()

        executor = ToolExecutor(mock_db)
        raw = executor.execute("download_and_install_mod", self.ARGS)
        result = json.loads(raw)

        assert "Success" in result
        assert "TestMod" in result


class TestExecuteShellCommand:
    """Test the execute_shell_command tool."""

    @patch("src.ai.tools.subprocess.run")
    def test_successful_command(self, mock_run):
        mock_run.return_value = MagicMock(stdout="hello world\n", stderr="")
        result = execute_shell({"command": "echo hello world"})
        assert "STDOUT:" in result
        assert "hello world" in result
        assert "STDERR:" in result
        mock_run.assert_called_once_with(
            "echo hello world", shell=True, capture_output=True, text=True, timeout=60
        )

    @patch("src.ai.tools.subprocess.run")
    def test_command_with_stderr(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="warning: something\n")
        result = execute_shell({"command": "some_cmd"})
        assert "STDOUT:" in result
        assert "STDERR:" in result
        assert "warning: something" in result

    @patch("src.ai.tools.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 999", timeout=60)
        result = execute_shell({"command": "sleep 999"})
        assert "Error" in result
        assert "timed out" in result

    @patch("src.ai.tools.subprocess.run")
    def test_general_exception(self, mock_run):
        mock_run.side_effect = OSError("Permission denied")
        result = execute_shell({"command": "restricted_cmd"})
        assert "Error" in result
        assert "Permission denied" in result

    @patch("src.ai.tools.subprocess.run")
    def test_via_tool_executor(self, mock_run):
        mock_run.return_value = MagicMock(stdout="output\n", stderr="")
        mock_db = MagicMock()
        executor = ToolExecutor(mock_db)
        raw = executor.execute("execute_shell_command", {"command": "echo output"})
        result = json.loads(raw)
        assert "STDOUT:" in result
        assert "output" in result
