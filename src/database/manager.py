"""
SQLite database manager for caching Nexus Mods data locally.

Stores mod metadata and requirements so the app works offline after the
initial sync and stays fast on subsequent lookups.
"""

import logging
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


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
            logger.info("Connecting to database: %s", self.db_path)
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON;")
            self._create_schema()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            logger.info("Closing database connection.")
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
                last_updated    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS requirements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mod_id          INTEGER NOT NULL REFERENCES mods(mod_id) ON DELETE CASCADE,
                required_mod_id INTEGER,          -- NULL if the mod is not in Nexus
                required_name   TEXT    NOT NULL,
                required_url    TEXT,
                is_patch        INTEGER NOT NULL DEFAULT 0  -- 1 = this is a compatibility patch
            );
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Mods
    # ------------------------------------------------------------------

    def upsert_mod(self, mod: dict) -> None:
        """Insert or replace a mod record."""
        try:
            self.conn.execute(
                """
                INSERT INTO mods
                    (mod_id, game_id, name, summary, description, version, author,
                     category_id, downloads, endorsements, picture_url, mod_url, last_updated)
                VALUES
                    (:mod_id, :game_id, :name, :summary, :description, :version, :author,
                     :category_id, :downloads, :endorsements, :picture_url, :mod_url, :last_updated)
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
                    last_updated = excluded.last_updated
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
                    "last_updated": mod.get(
                        "last_updated", datetime.now(timezone.utc).isoformat()
                    ),
                },
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            logger.error("SQL error upserting mod %s: %s", mod.get("mod_id"), exc)
            raise

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
        try:
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
        except sqlite3.Error as exc:
            logger.error("SQL error upserting requirements for mod %d: %s", mod_id, exc)
            raise

    def get_requirements(self, mod_id: int) -> list:
        rows = self.conn.execute(
            "SELECT * FROM requirements WHERE mod_id = ?", (mod_id,)
        ).fetchall()
        return [dict(r) for r in rows]
