"""Tests for the local Ollama AI agent."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.local_agent import (
    _build_user_prompt,
    _parse_response,
    analyse_mod,
    chat,
    DEFAULT_MODEL,
    _SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    CHAT_TOOLS,
)


class TestSystemPrompt:
    def test_prompt_asks_for_all_categories(self):
        assert "requirements" in _SYSTEM_PROMPT
        assert "patches" in _SYSTEM_PROMPT
        assert "known_issues" in _SYSTEM_PROMPT
        assert "load_order" in _SYSTEM_PROMPT
        assert "Hard dependencies" in _SYSTEM_PROMPT
        assert "incompatibilities" in _SYSTEM_PROMPT
        assert "load-order recommendations" in _SYSTEM_PROMPT


class TestChatSystemPrompt:
    def test_chat_prompt_is_skyrim_focused(self):
        assert "Skyrim" in CHAT_SYSTEM_PROMPT
        assert "App-nexus" in CHAT_SYSTEM_PROMPT
        assert "Do not talk about other games" in CHAT_SYSTEM_PROMPT

    def test_chat_tools_defined(self):
        tool_names = [t["function"]["name"] for t in CHAT_TOOLS]
        assert "search_mod_in_db" in tool_names
        assert "get_mod_requirements" in tool_names
        assert "get_loot_warnings" in tool_names


class TestBuildUserPrompt:
    def test_includes_all_sections(self):
        data = {
            "requirements_html": "<p>SKSE64</p>",
            "description_html": "<p>Cool mod</p>",
            "posts_html": "<p>Works great</p>",
        }
        prompt = _build_user_prompt(data)
        assert "REQUIREMENTS SECTION" in prompt
        assert "DESCRIPTION SECTION" in prompt
        assert "POSTS / COMMENTS" in prompt
        assert "SKSE64" in prompt

    def test_empty_data(self):
        prompt = _build_user_prompt({})
        assert "No mod page data was extracted" in prompt

    def test_partial_data(self):
        data = {"requirements_html": "<p>SkyUI</p>"}
        prompt = _build_user_prompt(data)
        assert "REQUIREMENTS SECTION" in prompt
        assert "DESCRIPTION SECTION" not in prompt


class TestParseResponse:
    def test_valid_json(self):
        raw = json.dumps({
            "requirements": ["SKSE64", "SkyUI"],
            "patches": ["Compatibility Patch"],
            "known_issues": ["Crashes with ENB"],
            "load_order": ["Load after USSEP"],
        })
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["patches"] == ["Compatibility Patch"]
        assert result["known_issues"] == ["Crashes with ENB"]
        assert result["load_order"] == ["Load after USSEP"]

    def test_json_with_code_fences(self):
        raw = '```json\n{"requirements": ["A"], "patches": [], "known_issues": [], "load_order": []}\n```'
        result = _parse_response(raw)
        assert result["requirements"] == ["A"]

    def test_invalid_json_returns_defaults(self):
        result = _parse_response("This is not JSON at all")
        assert result == {
            "requirements": [],
            "patches": [],
            "known_issues": [],
            "load_order": [],
        }

    def test_partial_keys(self):
        raw = json.dumps({"requirements": ["SKSE64"]})
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == []
        assert result["known_issues"] == []
        assert result["load_order"] == []


class TestAnalyseMod:
    @patch("src.ai.local_agent._import_ollama")
    def test_successful_analysis(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "requirements": ["SKSE64"],
                    "patches": [],
                    "known_issues": ["May crash on load"],
                    "load_order": ["Load after USSEP"],
                })
            }
        }
        mock_import.return_value = mock_ollama

        page_data = {"requirements_html": "<p>Requires SKSE64</p>"}
        result = analyse_mod(page_data)

        assert result["requirements"] == ["SKSE64"]
        assert result["known_issues"] == ["May crash on load"]
        assert result["load_order"] == ["Load after USSEP"]
        mock_ollama.chat.assert_called_once()

    @patch("src.ai.local_agent._import_ollama")
    def test_ollama_error_raises_runtime_error(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = Exception("Connection refused")
        mock_import.return_value = mock_ollama

        with pytest.raises(RuntimeError, match="Ollama analysis failed"):
            analyse_mod({"requirements_html": "<p>test</p>"})

    def test_import_error_when_ollama_missing(self):
        with patch.dict("sys.modules", {"ollama": None}):
            from src.ai import local_agent
            with pytest.raises(ImportError, match="Ollama Python package"):
                local_agent._import_ollama()


class TestChatToolCalling:
    """Test the chat() function's tool calling flow."""

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_with_tool_call_search_mod(self, mock_import):
        """Test that chat() executes search_mod_in_db tool and returns
        a final response after feeding tool results back to the model."""
        mock_ollama = MagicMock()

        # First call returns a tool_call request
        first_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.name = "search_mod_in_db"
        tool_call.function.arguments = {"mod_name": "SkyUI"}
        first_response.message.tool_calls = [tool_call]
        first_response.message.content = ""

        # Second call returns the final text response
        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "SkyUI is installed, version 5.2."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 3863, "name": "SkyUI", "version": "5.2"}
        ]

        reply, history = chat("Is SkyUI installed?", db=mock_db)

        assert reply == "SkyUI is installed, version 5.2."
        mock_db.search_mods_by_name.assert_called_once_with("SkyUI")
        assert mock_ollama.chat.call_count == 2

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_with_tool_call_get_requirements(self, mock_import):
        """Test get_mod_requirements tool execution."""
        mock_ollama = MagicMock()

        first_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.name = "get_mod_requirements"
        tool_call.function.arguments = {"nexus_id": 3863}
        first_response.message.tool_calls = [tool_call]

        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "SkyUI requires SKSE64."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.get_requirements.return_value = [
            {"required_name": "SKSE64", "is_patch": False}
        ]

        reply, history = chat("What does SkyUI need?", db=mock_db)

        assert reply == "SkyUI requires SKSE64."
        mock_db.get_requirements.assert_called_once_with(3863)

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_with_tool_call_get_loot_warnings(self, mock_import):
        """Test get_loot_warnings tool execution."""
        mock_ollama = MagicMock()

        first_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.name = "get_loot_warnings"
        tool_call.function.arguments = {"plugin_name": "SkyUI_SE.esp"}
        first_response.message.tool_calls = [tool_call]

        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "No warnings for SkyUI_SE.esp."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.get_loot_entry.return_value = {
            "name": "SkyUI_SE.esp",
            "msg": ["Requires SKSE64"],
        }

        reply, history = chat(
            "Any LOOT warnings for SkyUI_SE.esp?", db=mock_db
        )

        assert reply == "No warnings for SkyUI_SE.esp."
        mock_db.get_loot_entry.assert_called_once_with("SkyUI_SE.esp")

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_get_loot_warnings_not_found(self, mock_import):
        """Test get_loot_warnings when plugin is not in database."""
        mock_ollama = MagicMock()

        first_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.name = "get_loot_warnings"
        tool_call.function.arguments = {"plugin_name": "Missing.esp"}
        first_response.message.tool_calls = [tool_call]

        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "No LOOT data for that plugin."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.get_loot_entry.return_value = None

        reply, history = chat(
            "LOOT warnings for Missing.esp?", db=mock_db
        )

        assert reply == "No LOOT data for that plugin."
        # Verify the tool result message was appended with "not found" text
        tool_msgs = [m for m in history if isinstance(m, dict)
                     and m.get("role") == "tool"]
        assert any("No LOOT warnings found" in m["content"]
                    for m in tool_msgs)

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_no_tool_calls(self, mock_import):
        """Test simple conversation with no tool calls."""
        mock_ollama = MagicMock()

        response = MagicMock()
        response.message.tool_calls = None
        response.message.content = "Hello! How can I help with Skyrim mods?"

        mock_ollama.chat.return_value = response
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        reply, history = chat("Hello!", db=mock_db)

        assert reply == "Hello! How can I help with Skyrim mods?"
        assert mock_ollama.chat.call_count == 1

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_fallback_when_tools_not_supported(self, mock_import):
        """Test fallback behavior when model does not support tools."""
        mock_ollama = MagicMock()

        # First call raises because model doesn't support tools
        mock_ollama.chat.side_effect = [
            Exception("model does not support tool calling"),
            # Fallback call succeeds
            MagicMock(message=MagicMock(
                content="I can still help with Skyrim mods."
            )),
        ]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        reply, history = chat("Tell me about SkyUI", db=mock_db)

        assert reply == "I can still help with Skyrim mods."
        # Two calls: the failed tool call and the fallback
        assert mock_ollama.chat.call_count == 2

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_complete_failure_returns_error(self, mock_import):
        """Test that chat returns error message when both primary and
        fallback calls fail."""
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = Exception("Connection refused")
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        reply, history = chat("Hello", db=mock_db)

        assert "Error processing query" in reply

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_initializes_history_with_system_prompt(self, mock_import):
        """Test that chat creates history with system prompt when None."""
        mock_ollama = MagicMock()
        response = MagicMock()
        response.message.tool_calls = None
        response.message.content = "Hi!"
        mock_ollama.chat.return_value = response
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        _, history = chat("Hello", db=mock_db, history=None)

        # First message should be the system prompt
        assert history[0]["role"] == "system"
        assert "Skyrim" in history[0]["content"]
