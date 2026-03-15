"""Tests for local_agent.chat (Ollama function calling)."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.local_agent import chat, OLLAMA_TOOLS, _build_db_context, _chat_without_tools


class TestLocalChat:
    """Test the local_agent.chat function with tool calling."""

    @patch("src.ai.local_agent._import_ollama")
    def test_simple_reply_without_tool_calls(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {
            "message": {
                "role": "assistant",
                "content": "SkyUI requires SKSE64.",
            }
        }
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
        tool_call_response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_mod",
                            "arguments": {"name": "SkyUI"},
                        }
                    }
                ],
            }
        }
        # Second call: model produces a text reply
        final_response = {
            "message": {
                "role": "assistant",
                "content": "SkyUI is installed (version 5.2).",
            }
        }
        mock_ollama.chat.side_effect = [tool_call_response, final_response]
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
        mock_ollama.chat.return_value = {
            "message": {"role": "assistant", "content": "First reply."}
        }
        mock_import.return_value = mock_ollama
        mock_db = MagicMock()

        _, history = chat("Hello", db=mock_db)
        assert len(history) >= 3  # system + user + assistant

        # Second turn reuses history
        mock_ollama.chat.return_value = {
            "message": {"role": "assistant", "content": "Second reply."}
        }
        reply, history = chat("Follow up", db=mock_db, history=history)
        assert "Second reply" in reply
        # History should now have system + user + assistant + user + assistant
        user_msgs = [m for m in history if m.get("role") == "user"]
        assert len(user_msgs) == 2

    @patch("src.ai.local_agent._import_ollama")
    def test_chat_handles_multiple_tool_calls(self, mock_import):
        """Verify the loop handles multi-round tool calling."""
        mock_ollama = MagicMock()

        # Round 1: model calls search_mod
        round1 = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_mod",
                            "arguments": {"name": "Weapons"},
                        }
                    }
                ],
            }
        }
        # Round 2: model calls find_patches
        round2 = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "find_patches",
                            "arguments": {"mod_name": "Immersive Weapons"},
                        }
                    }
                ],
            }
        }
        # Round 3: final text
        round3 = {
            "message": {
                "role": "assistant",
                "content": "You need the USSEP patch for Immersive Weapons.",
            }
        }
        mock_ollama.chat.side_effect = [round1, round2, round3]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 50, "name": "Immersive Weapons", "version": "1.0",
             "author": "hothtrooper", "mod_url": ""}
        ]
        mock_db.get_requirements.return_value = [
            {"required_name": "USSEP Patch", "is_patch": 1, "required_url": ""}
        ]

        reply, _ = chat("What patches for Immersive Weapons?", db=mock_db)
        assert "USSEP" in reply or "patch" in reply.lower()
        assert mock_ollama.chat.call_count == 3


class TestBuildDbContext:
    """Tests for _build_db_context helper."""

    def test_returns_mod_list(self):
        mock_db = MagicMock()
        mock_db.get_all_mods.return_value = [
            {"name": "SkyUI", "version": "5.2"},
            {"name": "SKSE64", "version": "2.0"},
        ]
        ctx = _build_db_context(mock_db)
        assert "SkyUI" in ctx
        assert "SKSE64" in ctx
        assert "v5.2" in ctx

    def test_returns_empty_when_no_mods(self):
        mock_db = MagicMock()
        mock_db.get_all_mods.return_value = []
        assert _build_db_context(mock_db) == ""

    def test_returns_empty_on_exception(self):
        mock_db = MagicMock()
        mock_db.get_all_mods.side_effect = Exception("DB error")
        assert _build_db_context(mock_db) == ""

    def test_handles_missing_get_all_mods(self):
        """Object without get_all_mods attribute returns empty string."""
        mock_db = object()  # no get_all_mods
        assert _build_db_context(mock_db) == ""


class TestToolFallback:
    """Tests for fallback when model does not support tools."""

    @patch("src.ai.local_agent._import_ollama")
    def test_falls_back_when_tools_not_supported(self, mock_import):
        """chat() falls back to simple chat when model raises tool error."""
        mock_ollama = MagicMock()

        # First call (with tools) raises an error about tools
        mock_ollama.chat.side_effect = [
            Exception("llama3 does not support tools"),
            # Second call (without tools) succeeds
            {"message": {"role": "assistant", "content": "SkyUI is great."}},
        ]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.get_all_mods.return_value = [
            {"name": "SkyUI", "version": "5.2"},
        ]

        reply, history = chat("Tell me about SkyUI", db=mock_db)
        assert "SkyUI" in reply
        # Should have been called twice: once with tools (failed), once without
        assert mock_ollama.chat.call_count == 2
        # The second call should NOT have tools
        second_call = mock_ollama.chat.call_args_list[1]
        assert "tools" not in second_call.kwargs

    @patch("src.ai.local_agent._import_ollama")
    def test_fallback_includes_db_context_in_system_prompt(self, mock_import):
        """Fallback embeds mod list in the system prompt."""
        mock_ollama = MagicMock()

        mock_ollama.chat.side_effect = [
            Exception("model does not support tool use"),
            {"message": {"role": "assistant", "content": "Here's what I know."}},
        ]
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        mock_db.get_all_mods.return_value = [
            {"name": "USSEP", "version": "4.2"},
        ]

        reply, history = chat("What mods do I have?", db=mock_db)
        # The system message in the fallback history should mention USSEP
        system_msgs = [m for m in history if m.get("role") == "system"]
        assert any("USSEP" in m["content"] for m in system_msgs)

    @patch("src.ai.local_agent._import_ollama")
    def test_non_tool_error_is_reraised(self, mock_import):
        """Errors unrelated to tools should propagate normally."""
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = Exception("Connection refused")
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()
        with pytest.raises(Exception, match="Connection refused"):
            chat("Hello", db=mock_db)
