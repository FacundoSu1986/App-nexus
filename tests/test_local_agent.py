"""
Unit tests for the local Ollama AI agent (src/ai/local_agent.py).

All tests are offline — no real Ollama process or network is needed.
"""

import json

import pytest

from src.ai.local_agent import (
    _fallback,
    _parse_response,
    _strip_markdown_fences,
    _validate_schema,
    analyze_mod_content,
)


class TestStripMarkdownFences:
    def test_plain_json_unchanged(self):
        text = '{"requirements": [], "patches": [], "known_issues": []}'
        assert _strip_markdown_fences(text) == text

    def test_strips_json_fence(self):
        text = '```json\n{"requirements": [], "patches": [], "known_issues": []}\n```'
        result = _strip_markdown_fences(text)
        assert result == '{"requirements": [], "patches": [], "known_issues": []}'

    def test_strips_plain_fence(self):
        text = '```\n{"a": 1}\n```'
        result = _strip_markdown_fences(text)
        assert result == '{"a": 1}'

    def test_handles_extra_whitespace(self):
        text = '  ```json\n{"x": 1}\n```  '
        result = _strip_markdown_fences(text)
        assert result == '{"x": 1}'


class TestValidateSchema:
    def test_valid_data_passes(self):
        data = {"requirements": ["SKSE64"], "patches": [], "known_issues": ["Crash on load"]}
        result = _validate_schema(data)
        assert result["requirements"] == ["SKSE64"]
        assert result["known_issues"] == ["Crash on load"]

    def test_non_dict_returns_fallback(self):
        result = _validate_schema(["not", "a", "dict"])
        assert "error" in result

    def test_missing_key_returns_fallback(self):
        result = _validate_schema({"requirements": [], "patches": []})
        assert "error" in result

    def test_non_list_value_returns_fallback(self):
        result = _validate_schema({"requirements": "SKSE64", "patches": [], "known_issues": []})
        assert "error" in result

    def test_list_items_coerced_to_str(self):
        data = {"requirements": [1, 2], "patches": [], "known_issues": []}
        result = _validate_schema(data)
        assert result["requirements"] == ["1", "2"]


class TestParseResponse:
    def test_valid_json_response(self):
        raw = '{"requirements": ["SKSE64", "SkyUI"], "patches": ["Patch A"], "known_issues": []}'
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["patches"] == ["Patch A"]
        assert result["known_issues"] == []

    def test_json_with_markdown_fences(self):
        raw = (
            "```json\n"
            '{"requirements": ["SKSE64"], "patches": [], "known_issues": ["Conflict with ModX"]}'
            "\n```"
        )
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64"]
        assert result["known_issues"] == ["Conflict with ModX"]

    def test_invalid_json_returns_fallback(self):
        result = _parse_response("this is not json at all")
        assert "error" in result
        assert result["requirements"] == []

    def test_empty_string_returns_fallback(self):
        result = _parse_response("")
        assert "error" in result


class TestFallback:
    def test_fallback_structure(self):
        result = _fallback("Something went wrong")
        assert result["requirements"] == []
        assert result["patches"] == []
        assert result["known_issues"] == []
        assert result["error"] == "Something went wrong"


class TestAnalyzeModContentOffline:
    """Test analyze_mod_content when Ollama is not installed (import fails)."""

    def test_returns_fallback_when_ollama_not_installed(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "ollama":
                raise ImportError("No module named 'ollama'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = analyze_mod_content("some content")
        assert "error" in result
        assert result["requirements"] == []

    def test_returns_fallback_when_ollama_unreachable(self, monkeypatch):
        """Simulate Ollama installed but not running."""
        class MockOllama:
            @staticmethod
            def chat(**kwargs):
                raise ConnectionError("Ollama server not reachable")

        monkeypatch.setitem(__import__("sys").modules, "ollama", MockOllama())
        result = analyze_mod_content("some content")
        assert "error" in result
        assert result["requirements"] == []

    def test_returns_structured_result_when_ollama_responds(self, monkeypatch):
        """Simulate a successful Ollama response."""
        expected = {
            "requirements": ["SKSE64"],
            "patches": ["Patch for SkyUI"],
            "known_issues": [],
        }

        class MockOllama:
            @staticmethod
            def chat(**kwargs):
                return {"message": {"content": json.dumps(expected)}}

        monkeypatch.setitem(__import__("sys").modules, "ollama", MockOllama())
        result = analyze_mod_content("some content", model="llama3")
        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == ["Patch for SkyUI"]
        assert "error" not in result
