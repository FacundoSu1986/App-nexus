"""Tests for the Claude AI agent."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.claude_agent import (
    _build_user_prompt,
    _parse_response,
    analyse_mod,
    ATTRIBUTION,
    DEFAULT_MODEL,
)


class TestAttribution:
    def test_attribution_string(self):
        assert ATTRIBUTION == "Powered by Claude"


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

    def test_empty_data(self):
        prompt = _build_user_prompt({})
        assert "No mod page data was extracted" in prompt


class TestParseResponse:
    def test_valid_json(self):
        raw = json.dumps({
            "requirements": ["SKSE64"],
            "patches": ["Patch A"],
            "known_issues": ["Issue 1"],
        })
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == ["Patch A"]
        assert result["known_issues"] == ["Issue 1"]

    def test_json_with_code_fences(self):
        raw = '```json\n{"requirements": [], "patches": ["P"], "known_issues": []}\n```'
        result = _parse_response(raw)
        assert result["patches"] == ["P"]

    def test_invalid_json_returns_defaults(self):
        result = _parse_response("not json")
        assert result == {"requirements": [], "patches": [], "known_issues": []}


class TestAnalyseMod:
    @patch("src.ai.claude_agent._import_anthropic")
    def test_successful_analysis(self, mock_import):
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "requirements": ["SKSE64", "SkyUI"],
            "patches": [],
            "known_issues": [],
        })
        mock_message = MagicMock()
        mock_message.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        page_data = {"requirements_html": "<p>Requires SKSE64</p>"}
        result = analyse_mod(page_data, api_key="test-key-123")

        assert result["requirements"] == ["SKSE64", "SkyUI"]
        mock_anthropic.Anthropic.assert_called_once_with(api_key="test-key-123")

    @patch("src.ai.claude_agent._import_anthropic")
    def test_claude_error_raises_runtime_error(self, mock_import):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Invalid API key")

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_import.return_value = mock_anthropic

        with pytest.raises(RuntimeError, match="Claude analysis failed"):
            analyse_mod({"requirements_html": "<p>test</p>"}, api_key="bad-key")

    def test_import_error_when_anthropic_missing(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            from src.ai import claude_agent
            with pytest.raises(ImportError, match="Anthropic Python package"):
                claude_agent._import_anthropic()
