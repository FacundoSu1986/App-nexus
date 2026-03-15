"""Tests for the local Ollama AI agent."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.local_agent import (
    _build_user_prompt,
    _parse_response,
    analyse_mod,
    DEFAULT_MODEL,
    _SYSTEM_PROMPT,
)


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
        })
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["patches"] == ["Compatibility Patch"]
        assert result["known_issues"] == ["Crashes with ENB"]

    def test_json_with_code_fences(self):
        raw = '```json\n{"requirements": ["A"], "patches": [], "known_issues": []}\n```'
        result = _parse_response(raw)
        assert result["requirements"] == ["A"]

    def test_invalid_json_returns_defaults(self):
        result = _parse_response("This is not JSON at all")
        assert result == {"requirements": [], "patches": [], "known_issues": []}

    def test_partial_keys(self):
        raw = json.dumps({"requirements": ["SKSE64"]})
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == []
        assert result["known_issues"] == []


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
                })
            }
        }
        mock_import.return_value = mock_ollama

        page_data = {"requirements_html": "<p>Requires SKSE64</p>"}
        result = analyse_mod(page_data)

        assert result["requirements"] == ["SKSE64"]
        assert result["known_issues"] == ["May crash on load"]
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
