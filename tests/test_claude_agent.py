"""
Unit tests for the Claude API AI agent (src/ai/claude_agent.py).

All tests are offline — no real Anthropic API key or network is needed.
"""

import json

import pytest

from src.ai.claude_agent import (
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


class TestValidateSchema:
    def test_valid_data_passes(self):
        data = {"requirements": ["SKSE64"], "patches": [], "known_issues": ["Crash"]}
        result = _validate_schema(data)
        assert result["requirements"] == ["SKSE64"]

    def test_non_dict_returns_fallback(self):
        result = _validate_schema("a string")
        assert "error" in result

    def test_missing_key_returns_fallback(self):
        result = _validate_schema({"requirements": [], "patches": []})
        assert "error" in result

    def test_non_list_value_returns_fallback(self):
        result = _validate_schema({"requirements": "SKSE64", "patches": [], "known_issues": []})
        assert "error" in result


class TestParseResponse:
    def test_valid_json(self):
        raw = '{"requirements": ["SKSE64"], "patches": [], "known_issues": ["Conflict"]}'
        result = _parse_response(raw)
        assert result["requirements"] == ["SKSE64"]
        assert result["known_issues"] == ["Conflict"]

    def test_json_with_fences(self):
        raw = (
            "```json\n"
            '{"requirements": [], "patches": ["Patch"], "known_issues": []}'
            "\n```"
        )
        result = _parse_response(raw)
        assert result["patches"] == ["Patch"]

    def test_invalid_json_returns_fallback(self):
        result = _parse_response("not json")
        assert "error" in result


class TestFallback:
    def test_fallback_structure(self):
        result = _fallback("test error")
        assert result["requirements"] == []
        assert result["patches"] == []
        assert result["known_issues"] == []
        assert result["error"] == "test error"


class TestAnalyzeModContent:
    def test_returns_fallback_with_empty_api_key(self):
        result = analyze_mod_content("content", api_key="")
        assert "error" in result

    def test_returns_fallback_when_anthropic_not_installed(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = analyze_mod_content("content", api_key="sk-test-key")
        assert "error" in result
        assert result["requirements"] == []

    def test_returns_fallback_when_api_fails(self, monkeypatch):
        """Simulate an API error from Anthropic."""
        class MockMessage:
            content = [type("C", (), {"text": "not json"})()]

        class MockMessages:
            def create(self, **kwargs):
                raise RuntimeError("API connection failed")

        class MockAnthropic:
            def __init__(self, api_key):
                self.messages = MockMessages()

        import sys
        mock_module = type(sys)("anthropic")
        mock_module.Anthropic = MockAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mock_module)

        result = analyze_mod_content("some content", api_key="sk-test")
        assert "error" in result

    def test_returns_structured_result_on_success(self, monkeypatch):
        """Simulate a successful Claude response."""
        expected = {
            "requirements": ["SKSE64", "SkyUI"],
            "patches": [],
            "known_issues": ["Does not work with ModX"],
        }

        class MockContentItem:
            text = json.dumps(expected)

        class MockMessage:
            content = [MockContentItem()]

        class MockMessages:
            def create(self, **kwargs):
                return MockMessage()

        class MockAnthropic:
            def __init__(self, api_key):
                self.messages = MockMessages()

        import sys
        mock_module = type(sys)("anthropic")
        mock_module.Anthropic = MockAnthropic
        monkeypatch.setitem(sys.modules, "anthropic", mock_module)

        result = analyze_mod_content("some content", api_key="sk-test-key")
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["known_issues"] == ["Does not work with ModX"]
        assert "error" not in result
