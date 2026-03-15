"""Tests for the ai_mod_analysis table in DatabaseManager."""

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
    def test_table_exists_after_connect(self, db):
        tables = [
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "ai_mod_analysis" in tables

    def test_table_columns(self, db):
        columns = [
            row[1]
            for row in db.conn.execute(
                "PRAGMA table_info(ai_mod_analysis)"
            ).fetchall()
        ]
        assert "nexus_id" in columns
        assert "requirements" in columns
        assert "patches" in columns
        assert "known_issues" in columns
        assert "analyzed_by" in columns
        assert "last_analyzed" in columns


class TestUpsertAiAnalysis:
    def test_insert_and_get(self, db):
        analysis = {
            "nexus_id": "12345",
            "requirements": ["SKSE64", "SkyUI"],
            "patches": ["Compatibility Patch"],
            "known_issues": ["Crashes with ENB"],
            "analyzed_by": "ollama",
            "last_analyzed": "2024-06-01T12:00:00Z",
        }
        db.upsert_ai_analysis(analysis)
        result = db.get_ai_analysis("12345")

        assert result is not None
        assert result["nexus_id"] == "12345"
        assert result["requirements"] == ["SKSE64", "SkyUI"]
        assert result["patches"] == ["Compatibility Patch"]
        assert result["known_issues"] == ["Crashes with ENB"]
        assert result["analyzed_by"] == "ollama"
        assert result["last_analyzed"] == "2024-06-01T12:00:00Z"

    def test_update_replaces_existing(self, db):
        db.upsert_ai_analysis({
            "nexus_id": "100",
            "requirements": ["Old Req"],
            "patches": [],
            "known_issues": [],
            "analyzed_by": "ollama",
            "last_analyzed": "2024-01-01T00:00:00Z",
        })
        db.upsert_ai_analysis({
            "nexus_id": "100",
            "requirements": ["New Req"],
            "patches": ["Patch A"],
            "known_issues": ["Issue X"],
            "analyzed_by": "claude",
            "last_analyzed": "2024-06-15T10:30:00Z",
        })
        result = db.get_ai_analysis("100")

        assert result["requirements"] == ["New Req"]
        assert result["patches"] == ["Patch A"]
        assert result["known_issues"] == ["Issue X"]
        assert result["analyzed_by"] == "claude"

    def test_get_nonexistent_returns_none(self, db):
        assert db.get_ai_analysis("99999") is None

    def test_default_empty_lists(self, db):
        db.upsert_ai_analysis({
            "nexus_id": "200",
            "analyzed_by": "ollama",
            "last_analyzed": "2024-01-01T00:00:00Z",
        })
        result = db.get_ai_analysis("200")
        assert result["requirements"] == []
        assert result["patches"] == []
        assert result["known_issues"] == []

    def test_nexus_id_stored_as_string(self, db):
        db.upsert_ai_analysis({
            "nexus_id": "555",
            "requirements": ["A"],
            "patches": [],
            "known_issues": [],
            "analyzed_by": "claude",
            "last_analyzed": "2024-01-01T00:00:00Z",
        })
        # Query with string
        result = db.get_ai_analysis("555")
        assert result is not None
        assert result["nexus_id"] == "555"
