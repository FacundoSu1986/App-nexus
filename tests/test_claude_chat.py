"""Tests for claude_agent.chat (Anthropic tool_use function calling)."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.claude_agent import chat, ANTHROPIC_TOOLS


class TestClaudeChat:
    """Test the claude_agent.chat function with tool_use."""

    @patch("src.ai.claude_agent._import_anthropic")
    def test_simple_reply_without_tool_calls(self, mock_import):
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "SkyUI requires SKSE64."

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        mock_db = MagicMock()
        reply, history = chat(
            "What does SkyUI need?",
            db=mock_db,
            api_key="test-key",
        )

        assert "SKSE64" in reply
        assert len(history) >= 2  # user + assistant
        # Verify tools were passed
        call_kwargs = mock_client.messages.create.call_args
        assert "tools" in call_kwargs.kwargs or "tools" in (call_kwargs[1] if len(call_kwargs) > 1 else {})

    @patch("src.ai.claude_agent._import_anthropic")
    def test_chat_with_tool_use(self, mock_import):
        """Verify the model can call a tool and get results back."""
        # First response: model wants to use search_mod
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "search_mod"
        mock_tool_block.input = {"name": "SkyUI"}
        mock_tool_block.id = "tool_123"

        mock_response_1 = MagicMock()
        mock_response_1.content = [mock_tool_block]

        # Second response: final text
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "SkyUI is installed (version 5.2)."

        mock_response_2 = MagicMock()
        mock_response_2.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 1, "name": "SkyUI", "version": "5.2", "author": "schlangster"}
        ]

        reply, history = chat(
            "Is SkyUI installed?",
            db=mock_db,
            api_key="test-key",
        )

        assert "SkyUI" in reply
        assert mock_client.messages.create.call_count == 2
        mock_db.search_mods_by_name.assert_called_once_with("SkyUI")

    @patch("src.ai.claude_agent._import_anthropic")
    def test_chat_preserves_history(self, mock_import):
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "First reply."

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        mock_db = MagicMock()

        _, history = chat("Hello", db=mock_db, api_key="test-key")

        # Second turn
        mock_text_block_2 = MagicMock()
        mock_text_block_2.type = "text"
        mock_text_block_2.text = "Second reply."
        mock_response_2 = MagicMock()
        mock_response_2.content = [mock_text_block_2]
        mock_client.messages.create.return_value = mock_response_2

        reply, history = chat("Follow up", db=mock_db, api_key="test-key", history=history)
        assert "Second reply" in reply
        user_msgs = [m for m in history if m.get("role") == "user"]
        assert len(user_msgs) >= 2

    @patch("src.ai.claude_agent._import_anthropic")
    def test_chat_with_multiple_tool_rounds(self, mock_import):
        """Verify multi-round tool calling works."""
        # Round 1: tool call
        mock_tool_1 = MagicMock()
        mock_tool_1.type = "tool_use"
        mock_tool_1.name = "search_mod"
        mock_tool_1.input = {"name": "Weapons"}
        mock_tool_1.id = "tool_1"
        mock_resp_1 = MagicMock()
        mock_resp_1.content = [mock_tool_1]

        # Round 2: another tool call
        mock_tool_2 = MagicMock()
        mock_tool_2.type = "tool_use"
        mock_tool_2.name = "find_patches"
        mock_tool_2.input = {"mod_name": "Immersive Weapons"}
        mock_tool_2.id = "tool_2"
        mock_resp_2 = MagicMock()
        mock_resp_2.content = [mock_tool_2]

        # Round 3: final text
        mock_text = MagicMock()
        mock_text.type = "text"
        mock_text.text = "You need the USSEP patch for Immersive Weapons."
        mock_resp_3 = MagicMock()
        mock_resp_3.content = [mock_text]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [mock_resp_1, mock_resp_2, mock_resp_3]

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        mock_db = MagicMock()
        mock_db.search_mods_by_name.return_value = [
            {"mod_id": 50, "name": "Immersive Weapons", "version": "1.0",
             "author": "hothtrooper", "mod_url": ""}
        ]
        mock_db.get_requirements.return_value = [
            {"required_name": "USSEP Patch", "is_patch": 1, "required_url": ""}
        ]

        reply, _ = chat(
            "What patches for Immersive Weapons?",
            db=mock_db,
            api_key="test-key",
        )

        assert "USSEP" in reply or "patch" in reply.lower()
        assert mock_client.messages.create.call_count == 3
