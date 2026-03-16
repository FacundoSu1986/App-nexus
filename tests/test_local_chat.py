"""Tests for local_agent.chat (Ollama function calling)."""

import pytest
from unittest.mock import patch, MagicMock

from src.ai.local_agent import chat, CHAT_TOOLS, CHAT_SYSTEM_PROMPT


class TestLocalChat:
    """Test the local_agent.chat function with tool calling."""

    def test_chat_system_prompt_enforces_tools(self):
        """The system prompt must force tool use and forbid hallucinations."""
        assert "CRITICAL RULES" in CHAT_SYSTEM_PROMPT
        assert "NEVER guess or invent tools" in CHAT_SYSTEM_PROMPT
        for tool in CHAT_TOOLS:
            name = tool.get("function", {}).get("name")
            if name:
                assert name in CHAT_SYSTEM_PROMPT
        assert "tool calls properly" in CHAT_SYSTEM_PROMPT

    @patch("src.ai.local_agent._import_ollama")
    def test_system_prompt_is_sent_first(self, mock_import):
        """Ensure the chat call includes the sandboxing system prompt."""
        mock_ollama = MagicMock()
        response = MagicMock()
        response.message.tool_calls = None
        response.message.content = "ok"
        mock_ollama.chat.return_value = response
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        chat("Check dependencies", db=mock_db)

        called_args, called_kwargs = mock_ollama.chat.call_args
        messages = called_kwargs.get("messages")
        if not messages:
            pytest.fail("Ollama.chat was not called with messages")
        assert messages[0]["role"] == "system"
        assert CHAT_SYSTEM_PROMPT in messages[0]["content"]

    @patch("src.ai.local_agent._import_ollama")
    def test_simple_reply_without_tool_calls(self, mock_import):
        mock_ollama = MagicMock()
        response = MagicMock()
        response.message.tool_calls = None
        response.message.content = "SkyUI requires SKSE64."
        mock_ollama.chat.return_value = response
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        reply, history = chat("What does SkyUI need?", db=mock_db)

        assert "SKSE64" in reply
        assert len(history) >= 2  # system + user + assistant
        mock_ollama.chat.assert_called_once()
        # Verify tools were passed
        call_kwargs = mock_ollama.chat.call_args
        assert call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_with_tool_call(self, mock_import):
        """Verify the model can call a tool and get results back."""
        mock_ollama = MagicMock()

        # First call: model wants to use a tool
        first_response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.name = "search_mod_in_db"
        tool_call.function.arguments = {"mod_name": "SkyUI"}
        first_response.message.tool_calls = [tool_call]

        # Second call: model produces a text reply
        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "SkyUI is installed (version 5.2)."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 1, "name": "SkyUI", "version": "5.2", "author": "schlangster"}
        ]

        reply, history = chat("Is SkyUI installed?", db=mock_db)

        assert "SkyUI" in reply
        assert mock_ollama.chat.call_count == 2
        mock_db.search_mods_by_name.assert_called_once_with("SkyUI")

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_preserves_history(self, mock_import):
        mock_ollama = MagicMock()
        response1 = MagicMock()
        response1.message.tool_calls = None
        response1.message.content = "First reply."
        mock_ollama.chat.return_value = response1
        mock_import.return_value = mock_ollama
        mock_db = MagicMock()

        _, history = chat("Hello", db=mock_db)
        assert len(history) >= 3  # system + user + assistant

        # Second turn reuses history
        response2 = MagicMock()
        response2.message.tool_calls = None
        response2.message.content = "Second reply."
        mock_ollama.chat.return_value = response2
        reply, history = chat("Follow up", db=mock_db, history=history)
        assert "Second reply" in reply
        # History should now have system + user + assistant + user + assistant
        user_msgs = [m for m in history
                     if isinstance(m, dict) and m.get("role") == "user"]
        assert len(user_msgs) == 2

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_with_multiple_tool_calls_in_one_response(self, mock_import):
        """Verify multiple tool calls in a single response are all executed."""
        mock_ollama = MagicMock()

        # First call: model requests two tools at once
        first_response = MagicMock()
        tool_call_1 = MagicMock()
        tool_call_1.function.name = "search_mod_in_db"
        tool_call_1.function.arguments = {"mod_name": "Weapons"}
        tool_call_2 = MagicMock()
        tool_call_2.function.name = "get_loot_warnings"
        tool_call_2.function.arguments = {"plugin_name": "ImmersiveWeapons.esp"}
        first_response.message.tool_calls = [tool_call_1, tool_call_2]

        # Second call: final text
        final_response = MagicMock()
        final_response.message.tool_calls = None
        final_response.message.content = "Immersive Weapons has no LOOT warnings."

        mock_ollama.chat.side_effect = [first_response, final_response]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 50, "name": "Immersive Weapons", "version": "1.0"}
        ]
        mock_db.get_loot_entry.return_value = None

        reply, history = chat("What about Immersive Weapons?", db=mock_db)
        assert mock_ollama.chat.call_count == 2
        mock_db.search_mods_by_name.assert_called_once_with("Weapons")
        mock_db.get_loot_entry.assert_called_once_with("ImmersiveWeapons.esp")


class TestChatToolFallback:
    """Tests for fallback when model does not support tools."""

    @patch("src.ai.local_agent._import_ollama")
    def test_falls_back_when_tools_not_supported(self, mock_import):
        """chat() falls back to simple chat when model raises tool error."""
        mock_ollama = MagicMock()

        # First call (with tools) raises an error about tools
        mock_ollama.chat.side_effect = [
            Exception("llama3 does not support tools"),
            # Fallback call succeeds
            MagicMock(message=MagicMock(content="SkyUI is great.")),
        ]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        reply, history = chat("Tell me about SkyUI", db=mock_db)
        assert "SkyUI" in reply
        # Should have been called twice: once with tools (failed), once without
        assert mock_ollama.chat.call_count == 2
        # The second call should NOT have tools
        second_call = mock_ollama.chat.call_args_list[1]
        assert "tools" not in second_call.kwargs

    @patch("src.ai.local_agent._import_ollama")
    def test_non_tool_error_falls_back(self, mock_import):
        """All errors trigger fallback behavior in the new implementation."""
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = [
            Exception("Connection refused"),
            MagicMock(message=MagicMock(content="Fallback reply.")),
        ]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        reply, history = chat("Hello", db=mock_db)
        assert reply == "Fallback reply."

    @patch("src.ai.local_agent._import_ollama")
    def test_complete_failure_returns_error_string(self, mock_import):
        """When both primary and fallback calls fail, return error message."""
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = Exception("Connection refused")
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        reply, history = chat("Hello", db=mock_db)
        assert "Error processing query" in reply
