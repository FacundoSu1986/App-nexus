"""Tests for the local Ollama AI agent."""

import json

import pytest
from unittest.mock import patch, MagicMock

from src.ai.local_agent import (
    _build_user_prompt,
    _parse_response,
    analyse_mod,
    analyse_and_cache_mod,
    DEFAULT_MODEL,
    _SYSTEM_PROMPT,
    _CACHE_SYSTEM_PROMPT,
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


class TestCacheSystemPrompt:
    def test_prompt_asks_for_all_categories(self):
        assert "requirements" in _CACHE_SYSTEM_PROMPT
        assert "patches" in _CACHE_SYSTEM_PROMPT
        assert "known_issues" in _CACHE_SYSTEM_PROMPT
        assert "load_order" in _CACHE_SYSTEM_PROMPT


class TestAnalyseAndCacheMod:
    @patch("src.ai.local_agent._import_ollama")
    def test_successful_analysis_and_cache(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "requirements": ["SKSE64"],
                    "patches": ["Patch A"],
                    "known_issues": ["Bug X"],
                    "load_order": ["Load after USSEP"],
                })
            }
        }
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        result = analyse_and_cache_mod(
            nexus_id="12345",
            description="<p>Requires SKSE64</p>",
            sticky_posts=["Load after USSEP"],
            db=mock_db,
        )

        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == ["Patch A"]
        assert result["known_issues"] == ["Bug X"]
        assert result["load_order"] == ["Load after USSEP"]
        mock_db.upsert_ai_analysis.assert_called_once()

        # Verify the record passed to upsert
        call_args = mock_db.upsert_ai_analysis.call_args[0][0]
        assert call_args["nexus_id"] == "12345"
        assert call_args["analyzed_by"] == "ollama"
        assert call_args["last_analyzed"] != ""

    @patch("src.ai.local_agent._import_ollama")
    def test_ollama_failure_returns_defaults_and_still_caches(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = Exception("Connection refused")
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        result = analyse_and_cache_mod(
            nexus_id="999",
            description="Some description",
            sticky_posts=[],
            db=mock_db,
        )

        assert result["requirements"] == []
        assert result["patches"] == []
        assert result["known_issues"] == []
        assert result["load_order"] == []
        # Should still cache the empty result
        mock_db.upsert_ai_analysis.assert_called_once()

    @patch("src.ai.local_agent._import_ollama")
    def test_empty_inputs(self, mock_import):
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "requirements": [],
                    "patches": [],
                    "known_issues": [],
                    "load_order": [],
                })
            }
        }
        mock_import.return_value = mock_ollama

        mock_db = MagicMock()

        result = analyse_and_cache_mod(
            nexus_id="500",
            description="",
            sticky_posts=[],
            db=mock_db,
        )

        assert result == {
            "requirements": [],
            "patches": [],
            "known_issues": [],
            "load_order": [],
        }
        mock_db.upsert_ai_analysis.assert_called_once()
