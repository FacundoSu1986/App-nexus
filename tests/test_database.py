"""Tests for DatabaseManager."""

import threading

import pytest

from src.database.manager import DatabaseManager


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path=path)
    manager.connect()
    yield manager
    manager.close()


class TestSchema:
    def test_connect_creates_tables(self, db):
        tables = [
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "mods" in tables
        assert "requirements" in tables


class TestMods:
    def _sample_mod(self, mod_id=1000):
        return {
            "mod_id": mod_id,
            "game_id": 1704,
            "name": "Test Mod",
            "summary": "A test mod",
            "description": "Full description",
            "version": "1.0",
            "author": "Tester",
            "category_id": 5,
            "downloads": 100,
            "endorsements": 50,
            "picture_url": "https://example.com/img.jpg",
            "mod_url": "https://www.nexusmods.com/skyrimspecialedition/mods/1000",
            "last_updated": "2024-01-01T00:00:00",
        }

    def test_upsert_and_get_mod(self, db):
        db.upsert_mod(self._sample_mod())
        mod = db.get_mod(1000)
        assert mod is not None
        assert mod["name"] == "Test Mod"
        assert mod["author"] == "Tester"

    def test_upsert_updates_existing(self, db):
        db.upsert_mod(self._sample_mod())
        updated = self._sample_mod()
        updated["name"] = "Test Mod Updated"
        db.upsert_mod(updated)
        mod = db.get_mod(1000)
        assert mod["name"] == "Test Mod Updated"

    def test_get_mod_returns_none_for_missing(self, db):
        assert db.get_mod(99999) is None

    def test_search_mods_by_name(self, db):
        db.upsert_mod(self._sample_mod(1001))
        results = db.search_mods_by_name("Test")
        assert len(results) >= 1
        assert any(r["mod_id"] == 1001 for r in results)

    def test_search_mods_case_insensitive(self, db):
        db.upsert_mod(self._sample_mod(1002))
        results = db.search_mods_by_name("test mod")
        assert any(r["mod_id"] == 1002 for r in results)

    def test_get_all_mods(self, db):
        db.upsert_mod(self._sample_mod(2001))
        db.upsert_mod(self._sample_mod(2002))
        all_mods = db.get_all_mods()
        ids = [m["mod_id"] for m in all_mods]
        assert 2001 in ids
        assert 2002 in ids


class TestRequirements:
    def test_upsert_and_get_requirements(self, db):
        db.upsert_mod(
            {
                "mod_id": 500,
                "name": "ModA",
                "last_updated": "2024-01-01T00:00:00",
            }
        )
        reqs = [
            {"required_name": "SKSE64", "required_url": "https://...", "is_patch": False},
            {"required_name": "SkyUI Patch", "required_url": "", "is_patch": True},
        ]
        db.upsert_requirements(500, reqs)
        stored = db.get_requirements(500)
        assert len(stored) == 2
        names = {r["required_name"] for r in stored}
        assert "SKSE64" in names
        assert "SkyUI Patch" in names

    def test_upsert_requirements_replaces_old(self, db):
        db.upsert_mod({"mod_id": 501, "name": "ModB", "last_updated": "2024-01-01"})
        db.upsert_requirements(501, [{"required_name": "Old Req", "is_patch": False}])
        db.upsert_requirements(501, [{"required_name": "New Req", "is_patch": False}])
        stored = db.get_requirements(501)
        assert len(stored) == 1
        assert stored[0]["required_name"] == "New Req"


class TestContextManager:
    def test_context_manager(self, tmp_path):
        path = str(tmp_path / "ctx.db")
        with DatabaseManager(db_path=path) as db:
            db.upsert_mod({"mod_id": 1, "name": "CTX Mod", "last_updated": "2024-01-01"})
            assert db.get_mod(1) is not None
        # After __exit__ the connection should be closed
        assert db._connection is None


class TestThreadSafety:
    """Verify that a thread-local DatabaseManager can safely access the same DB file."""

    def test_thread_local_db_writes_visible_after_close(self, tmp_path):
        """A separate DatabaseManager in a background thread can write data
        that is visible from the main-thread connection after both close/reopen."""
        db_path = str(tmp_path / "thread.db")

        # Main-thread connection — seed schema
        main_db = DatabaseManager(db_path=db_path)
        main_db.connect()

        error_holder = []

        def background_work():
            try:
                thread_db = DatabaseManager(db_path=db_path)
                thread_db.connect()
                try:
                    thread_db.upsert_mod(
                        {"mod_id": 42, "name": "ThreadMod", "last_updated": "2024-01-01"}
                    )
                finally:
                    thread_db.close()
            except Exception as exc:
                error_holder.append(exc)

        t = threading.Thread(target=background_work)
        t.start()
        t.join()

        assert not error_holder, f"Background thread raised: {error_holder[0]}"

        # Refresh main connection to see the new data
        main_db.close()
        main_db.connect()
        mod = main_db.get_mod(42)
        main_db.close()

        assert mod is not None
        assert mod["name"] == "ThreadMod"

    def test_thread_local_db_does_not_share_connection(self, tmp_path):
        """Two DatabaseManager instances on different threads use distinct connections."""
        db_path = str(tmp_path / "thread2.db")

        main_db = DatabaseManager(db_path=db_path)
        main_db.connect()

        thread_conn_ids = []

        def capture_conn_id():
            thread_db = DatabaseManager(db_path=db_path)
            thread_db.connect()
            thread_conn_ids.append(id(thread_db.conn))
            thread_db.close()

        t = threading.Thread(target=capture_conn_id)
        t.start()
        t.join()

        assert len(thread_conn_ids) == 1
        assert thread_conn_ids[0] != id(main_db.conn)
        main_db.close()
