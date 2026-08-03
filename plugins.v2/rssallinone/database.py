"""SQLite persistence for durable plugin state and future workflow recovery."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteStore:
    """Small repository layer with one connection per operation."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._migration_lock = threading.Lock()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._migration_lock:
            with self.connection() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS media_items (
                        id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        media_type TEXT,
                        title TEXT NOT NULL DEFAULT '',
                        source_name TEXT NOT NULL DEFAULT '',
                        source_path TEXT NOT NULL DEFAULT '',
                        downloader_id TEXT NOT NULL DEFAULT '',
                        info_hash TEXT NOT NULL DEFAULT '',
                        tmdb_id INTEGER,
                        season INTEGER CHECK (season IS NULL OR season >= 0),
                        category TEXT NOT NULL DEFAULT '',
                        target_name TEXT NOT NULL DEFAULT '',
                        failure_code TEXT NOT NULL DEFAULT '',
                        failure_message TEXT NOT NULL DEFAULT '',
                        rolled_back INTEGER NOT NULL DEFAULT 0,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_media_items_state
                        ON media_items(state, updated_at DESC);

                    CREATE TABLE IF NOT EXISTS torrent_snapshots (
                        downloader_id TEXT NOT NULL,
                        info_hash TEXT NOT NULL,
                        name TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT '',
                        content_path TEXT NOT NULL DEFAULT '',
                        progress REAL NOT NULL DEFAULT 0,
                        size INTEGER NOT NULL DEFAULT 0,
                        media_id TEXT,
                        source_url_masked TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (downloader_id, info_hash),
                        FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE SET NULL
                    );

                    CREATE TABLE IF NOT EXISTS rss_tasks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        position INTEGER NOT NULL DEFAULT 0,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS rss_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        source_key TEXT NOT NULL,
                        content_key TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL,
                        reason TEXT NOT NULL DEFAULT '',
                        detail_url_masked TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (task_id, source_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_rss_history_created
                        ON rss_history(created_at DESC);

                    CREATE TABLE IF NOT EXISTS background_tasks (
                        id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        current_item TEXT NOT NULL DEFAULT '',
                        processed INTEGER NOT NULL DEFAULT 0,
                        succeeded INTEGER NOT NULL DEFAULT 0,
                        failed INTEGER NOT NULL DEFAULT 0,
                        total INTEGER NOT NULL DEFAULT 0,
                        result_json TEXT NOT NULL DEFAULT '{}',
                        error_message TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        finished_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS import_watches (
                        id TEXT PRIMARY KEY,
                        media_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        local_hardlink_path TEXT NOT NULL DEFAULT '',
                        expected_cd2_dest_path TEXT NOT NULL DEFAULT '',
                        expected_mp_library_path TEXT NOT NULL DEFAULT '',
                        cd2_key TEXT NOT NULL DEFAULT '',
                        file_size INTEGER NOT NULL DEFAULT 0,
                        transferred_bytes INTEGER NOT NULL DEFAULT 0,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action TEXT NOT NULL,
                        actor TEXT NOT NULL DEFAULT '',
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    );
                    """
                )
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )

    def health(self) -> Dict[str, Any]:
        with self.connection() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            version_row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
        return {
            "ready": integrity == "ok",
            "integrity": integrity,
            "schema_version": int(version_row[0]),
            "path": str(self.path),
        }

    def counts(self) -> Dict[str, int]:
        tables = {
            "media": "media_items",
            "torrents": "torrent_snapshots",
            "rss_tasks": "rss_tasks",
            "rss_history": "rss_history",
            "background_tasks": "background_tasks",
            "import_watches": "import_watches",
        }
        with self.connection() as connection:
            return {
                key: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for key, table in tables.items()
            }

    @staticmethod
    def _page(offset: object, limit: object) -> Tuple[int, int]:
        try:
            safe_offset = max(0, int(offset or 0))
        except (TypeError, ValueError):
            safe_offset = 0
        try:
            safe_limit = max(1, min(int(limit or 50), 200))
        except (TypeError, ValueError):
            safe_limit = 50
        return safe_offset, safe_limit

    def list_media(
        self,
        state: str = "",
        media_type: str = "",
        offset: object = 0,
        limit: object = 50,
    ) -> Dict[str, Any]:
        safe_offset, safe_limit = self._page(offset, limit)
        clauses: List[str] = []
        params: List[Any] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM media_items {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM media_items {where}
                    ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                [*params, safe_limit, safe_offset],
            ).fetchall()
        return self._result(rows, total, safe_offset, safe_limit)

    def list_torrents(self, offset: object = 0, limit: object = 50) -> Dict[str, Any]:
        return self._list_table("torrent_snapshots", "updated_at", offset, limit)

    def list_rss_tasks(self, offset: object = 0, limit: object = 100) -> Dict[str, Any]:
        safe_offset, safe_limit = self._page(offset, limit)
        with self.connection() as connection:
            total = connection.execute("SELECT COUNT(*) FROM rss_tasks").fetchone()[0]
            rows = connection.execute(
                """SELECT * FROM rss_tasks
                   ORDER BY position ASC, created_at ASC LIMIT ? OFFSET ?""",
                (safe_limit, safe_offset),
            ).fetchall()
        return self._result(rows, total, safe_offset, safe_limit)

    def list_rss_history(self, offset: object = 0, limit: object = 50) -> Dict[str, Any]:
        return self._list_table("rss_history", "created_at", offset, limit)

    def list_background_tasks(self, offset: object = 0, limit: object = 50) -> Dict[str, Any]:
        return self._list_table("background_tasks", "updated_at", offset, limit)

    def _list_table(
        self,
        table: str,
        order_column: str,
        offset: object,
        limit: object,
    ) -> Dict[str, Any]:
        safe_offset, safe_limit = self._page(offset, limit)
        with self.connection() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM {table} ORDER BY {order_column} DESC LIMIT ? OFFSET ?",
                (safe_limit, safe_offset),
            ).fetchall()
        return self._result(rows, total, safe_offset, safe_limit)

    @staticmethod
    def _result(
        rows: List[sqlite3.Row],
        total: int,
        offset: int,
        limit: int,
    ) -> Dict[str, Any]:
        items = []
        for row in rows:
            item = dict(row)
            for key in tuple(item):
                if key.endswith("_json"):
                    try:
                        item[key.removesuffix("_json")] = json.loads(item[key] or "{}")
                    except (TypeError, json.JSONDecodeError):
                        item[key.removesuffix("_json")] = {}
                    del item[key]
            items.append(item)
        return {"items": items, "total": int(total), "offset": offset, "limit": limit}
