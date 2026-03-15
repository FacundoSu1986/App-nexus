"""
Tests for the AI mod analysis DB functions added to DatabaseManager.
"""

import json
from datetime import datetime, timezone

import pytest

from src.database.manager import DatabaseManager


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_ai.db")
    manager = DatabaseManager(db_path=path)
    manager.connect()
    yield manager
    manager.close()


class TestAiModAnalysisSchema:
    def test_table_created(self, db):
        tables = [
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "ai_mod_analysis" in tables


class TestUpsertAndGetAiAnalysis:
    def _sample_analysis(self):
        return {
            "requirements": ["SKSE64", "SkyUI"],
            "patches": ["SkyUI Patch"],
            "known_issues": ["Crashes with ModX"],
        }

    def test_upsert_and_get(self, db):
        db.upsert_ai_analysis("12345", self._sample_analysis(), analyzed_by="ollama")
        result = db.get_ai_analysis("12345")
        assert result is not None
        assert result["nexus_id"] == "12345"
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["patches"] == ["SkyUI Patch"]
        assert result["known_issues"] == ["Crashes with ModX"]
        assert result["analyzed_by"] == "ollama"
        assert result["last_analyzed"]  # non-empty ISO timestamp

    def test_upsert_updates_existing(self, db):
        db.upsert_ai_analysis("999", self._sample_analysis(), analyzed_by="ollama")
        updated = {"requirements": ["SKSE64"], "patches": [], "known_issues": []}
        db.upsert_ai_analysis("999", updated, analyzed_by="claude")
        result = db.get_ai_analysis("999")
        assert result["requirements"] == ["SKSE64"]
        assert result["patches"] == []
        assert result["analyzed_by"] == "claude"

    def test_get_returns_none_for_missing(self, db):
        assert db.get_ai_analysis("no-such-id") is None

    def test_last_analyzed_is_iso_timestamp(self, db):
        db.upsert_ai_analysis("111", self._sample_analysis(), analyzed_by="ollama")
        result = db.get_ai_analysis("111")
        # Should parse as a valid datetime
        dt = datetime.fromisoformat(result["last_analyzed"])
        assert dt is not None

    def test_empty_lists_stored_correctly(self, db):
        analysis = {"requirements": [], "patches": [], "known_issues": []}
        db.upsert_ai_analysis("222", analysis, analyzed_by="claude")
        result = db.get_ai_analysis("222")
        assert result["requirements"] == []
        assert result["patches"] == []
        assert result["known_issues"] == []

    def test_nexus_id_stored_as_string(self, db):
        analysis = {"requirements": ["SKSE64"], "patches": [], "known_issues": []}
        db.upsert_ai_analysis(333, analysis, analyzed_by="ollama")
        result = db.get_ai_analysis("333")
        assert result is not None
        assert result["nexus_id"] == "333"
