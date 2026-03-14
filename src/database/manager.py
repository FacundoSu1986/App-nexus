"""
SQLite database manager for caching Nexus Mods data locally.

Stores mod metadata, requirements, and user-reported issues so the app works
offline after the initial sync and stays fast on subsequent lookups.
"""

import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional


def _get_default_db_path() -> str:
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    folder = os.path.join(app_data, "AppNexus")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "app_nexus.db")


class DatabaseManager:
    """Manages the local SQLite cache of Nexus Mods data."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _get_default_db_path()
        self._connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open (or reuse) the database connection and ensure schema exists."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON;")
            self._create_schema()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mods (
                mod_id          INTEGER PRIMARY KEY,
                game_id         INTEGER NOT NULL DEFAULT 1704,   -- 1704 = Skyrim SE
                name            TEXT    NOT NULL,
                summary         TEXT,
                description     TEXT,
                version         TEXT,
                author          TEXT,
                category_id     INTEGER,
                downloads       INTEGER DEFAULT 0,
                endorsements    INTEGER DEFAULT 0,
                picture_url     TEXT,
                mod_url         TEXT,
                last_scraped    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS requirements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_id          INTEGER NOT NULL REFERENCES mods(mod_id) ON DELETE CASCADE,
                required_mod_id INTEGER,          -- NULL if the mod is not in Nexus
                required_name   TEXT    NOT NULL,
                required_url    TEXT,
                is_patch        INTEGER NOT NULL DEFAULT 0  -- 1 = this is a compatibility patch
            );

            CREATE TABLE IF NOT EXISTS incompatibilities (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_id          INTEGER NOT NULL REFERENCES mods(mod_id) ON DELETE CASCADE,
                incompatible_mod_id INTEGER,
                incompatible_name   TEXT NOT NULL,
                reason              TEXT
            );

            CREATE TABLE IF NOT EXISTS issues (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_id          INTEGER NOT NULL REFERENCES mods(mod_id) ON DELETE CASCADE,
                title           TEXT    NOT NULL,
                body            TEXT,
                author          TEXT,
                posted_at       TEXT,
                url             TEXT
            );

            CREATE TABLE IF NOT EXISTS load_order_rules (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_id          INTEGER NOT NULL REFERENCES mods(mod_id) ON DELETE CASCADE,
                rule_type       TEXT    NOT NULL,  -- 'AFTER' | 'BEFORE'
                target_mod_name TEXT    NOT NULL,
                notes           TEXT
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Mods
    # ------------------------------------------------------------------

    def upsert_mod(self, mod: dict) -> None:
        """Insert or replace a mod record."""
        self.conn.execute(
            """
            INSERT INTO mods
                (mod_id, game_id, name, summary, description, version, author,
                 category_id, downloads, endorsements, picture_url, mod_url, last_scraped)
            VALUES
                (:mod_id, :game_id, :name, :summary, :description, :version, :author,
                 :category_id, :downloads, :endorsements, :picture_url, :mod_url, :last_scraped)
            ON CONFLICT(mod_id) DO UPDATE SET
                name         = excluded.name,
                summary      = excluded.summary,
                description  = excluded.description,
                version      = excluded.version,
                author       = excluded.author,
                category_id  = excluded.category_id,
                downloads    = excluded.downloads,
                endorsements = excluded.endorsements,
                picture_url  = excluded.picture_url,
                mod_url      = excluded.mod_url,
                last_scraped = excluded.last_scraped
            """,
            {
                "mod_id": mod["mod_id"],
                "game_id": mod.get("game_id", 1704),
                "name": mod["name"],
                "summary": mod.get("summary", ""),
                "description": mod.get("description", ""),
                "version": mod.get("version", ""),
                "author": mod.get("author", ""),
                "category_id": mod.get("category_id"),
                "downloads": mod.get("downloads", 0),
                "endorsements": mod.get("endorsements", 0),
                "picture_url": mod.get("picture_url", ""),
                "mod_url": mod.get("mod_url", ""),
                "last_scraped": mod.get("last_scraped", datetime.now(timezone.utc).isoformat()),
            },
        )
        self.conn.commit()

    def get_mod(self, mod_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM mods WHERE mod_id = ?", (mod_id,)
        ).fetchone()
        return dict(row) if row else None

    def search_mods_by_name(self, name: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM mods WHERE name LIKE ?", (f"%{name}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_mods(self) -> list:
        rows = self.conn.execute("SELECT * FROM mods ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    def upsert_requirements(self, mod_id: int, requirements: list) -> None:
        """Replace all requirements for a given mod."""
        self.conn.execute("DELETE FROM requirements WHERE mod_id = ?", (mod_id,))
        self.conn.executemany(
            """
            INSERT INTO requirements
                (mod_id, required_mod_id, required_name, required_url, is_patch)
            VALUES
                (:mod_id, :required_mod_id, :required_name, :required_url, :is_patch)
            """,
            [
                {
                    "mod_id": mod_id,
                    "required_mod_id": r.get("required_mod_id"),
                    "required_name": r["required_name"],
                    "required_url": r.get("required_url", ""),
                    "is_patch": int(r.get("is_patch", False)),
                }
                for r in requirements
            ],
        )
        self.conn.commit()

    def get_requirements(self, mod_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM requirements WHERE mod_id = ?", (mod_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Incompatibilities
    # ------------------------------------------------------------------

    def upsert_incompatibilities(self, mod_id: int, incompatibilities: list) -> None:
        self.conn.execute(
            "DELETE FROM incompatibilities WHERE mod_id = ?", (mod_id,)
        )
        self.conn.executemany(
            """
            INSERT INTO incompatibilities
                (mod_id, incompatible_mod_id, incompatible_name, reason)
            VALUES
                (:mod_id, :incompatible_mod_id, :incompatible_name, :reason)
            """,
            [
                {
                    "mod_id": mod_id,
                    "incompatible_mod_id": i.get("incompatible_mod_id"),
                    "incompatible_name": i["incompatible_name"],
                    "reason": i.get("reason", ""),
                }
                for i in incompatibilities
            ],
        )
        self.conn.commit()

    def get_incompatibilities(self, mod_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM incompatibilities WHERE mod_id = ?", (mod_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Issues / comments
    # ------------------------------------------------------------------

    def upsert_issues(self, mod_id: int, issues: list) -> None:
        self.conn.execute("DELETE FROM issues WHERE mod_id = ?", (mod_id,))
        self.conn.executemany(
            """
            INSERT INTO issues (mod_id, title, body, author, posted_at, url)
            VALUES (:mod_id, :title, :body, :author, :posted_at, :url)
            """,
            [
                {
                    "mod_id": mod_id,
                    "title": i["title"],
                    "body": i.get("body", ""),
                    "author": i.get("author", ""),
                    "posted_at": i.get("posted_at", ""),
                    "url": i.get("url", ""),
                }
                for i in issues
            ],
        )
        self.conn.commit()

    def get_issues(self, mod_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM issues WHERE mod_id = ? ORDER BY posted_at DESC",
            (mod_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Load-order rules
    # ------------------------------------------------------------------

    def upsert_load_order_rules(self, mod_id: int, rules: list) -> None:
        self.conn.execute(
            "DELETE FROM load_order_rules WHERE mod_id = ?", (mod_id,)
        )
        self.conn.executemany(
            """
            INSERT INTO load_order_rules (mod_id, rule_type, target_mod_name, notes)
            VALUES (:mod_id, :rule_type, :target_mod_name, :notes)
            """,
            [
                {
                    "mod_id": mod_id,
                    "rule_type": r["rule_type"],
                    "target_mod_name": r["target_mod_name"],
                    "notes": r.get("notes", ""),
                }
                for r in rules
            ],
        )
        self.conn.commit()

    def get_load_order_rules(self, mod_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM load_order_rules WHERE mod_id = ?", (mod_id,)
        ).fetchall()
        return [dict(r) for r in rows]
