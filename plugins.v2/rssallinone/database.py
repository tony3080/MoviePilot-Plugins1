"""SQLite persistence for durable plugin state and future workflow recovery."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple


SCHEMA_VERSION = 3


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
                        present INTEGER NOT NULL DEFAULT 1,
                        recognition_state TEXT NOT NULL DEFAULT 'pending',
                        inventory_state TEXT NOT NULL DEFAULT 'unknown',
                        media_title TEXT NOT NULL DEFAULT '',
                        media_type TEXT NOT NULL DEFAULT '',
                        media_year TEXT NOT NULL DEFAULT '',
                        tmdb_id INTEGER,
                        season INTEGER CHECK (season IS NULL OR season >= 0),
                        poster TEXT NOT NULL DEFAULT '',
                        recognition_error TEXT NOT NULL DEFAULT '',
                        recognized_at TEXT,
                        last_seen_at TEXT NOT NULL DEFAULT '',
                        missing_since TEXT,
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

                    CREATE TABLE IF NOT EXISTS file_mappings (
                        downloader_id TEXT NOT NULL,
                        info_hash TEXT NOT NULL,
                        file_index INTEGER NOT NULL,
                        media_id TEXT NOT NULL DEFAULT '',
                        source_relative_path TEXT NOT NULL DEFAULT '',
                        current_source_path TEXT NOT NULL DEFAULT '',
                        new_rel TEXT NOT NULL DEFAULT '',
                        local_hardlink_path TEXT NOT NULL DEFAULT '',
                        inventory_path TEXT NOT NULL DEFAULT '',
                        inventory_exists INTEGER NOT NULL DEFAULT 0,
                        file_size INTEGER NOT NULL DEFAULT 0,
                        state TEXT NOT NULL DEFAULT 'planned',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (downloader_id, info_hash, file_index)
                    );
                    CREATE INDEX IF NOT EXISTS idx_file_mappings_media
                        ON file_mappings(media_id, state, updated_at DESC);

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
                self._migrate_v2(connection)
                self._migrate_v3(connection)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utc_now()),
                )

    @staticmethod
    def _migrate_v2(connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(torrent_snapshots)").fetchall()
        }
        additions = {
            "present": "INTEGER NOT NULL DEFAULT 1",
            "recognition_state": "TEXT NOT NULL DEFAULT 'pending'",
            "inventory_state": "TEXT NOT NULL DEFAULT 'unknown'",
            "media_title": "TEXT NOT NULL DEFAULT ''",
            "media_type": "TEXT NOT NULL DEFAULT ''",
            "media_year": "TEXT NOT NULL DEFAULT ''",
            "tmdb_id": "INTEGER",
            "season": "INTEGER",
            "poster": "TEXT NOT NULL DEFAULT ''",
            "recognition_error": "TEXT NOT NULL DEFAULT ''",
            "recognized_at": "TEXT",
            "last_seen_at": "TEXT NOT NULL DEFAULT ''",
            "missing_since": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE torrent_snapshots ADD COLUMN {name} {definition}"
                )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_torrent_snapshots_present
               ON torrent_snapshots(present, downloader_id, updated_at DESC)"""
        )

    @staticmethod
    def _migrate_v3(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS file_mappings (
                downloader_id TEXT NOT NULL,
                info_hash TEXT NOT NULL,
                file_index INTEGER NOT NULL,
                media_id TEXT NOT NULL DEFAULT '',
                source_relative_path TEXT NOT NULL DEFAULT '',
                current_source_path TEXT NOT NULL DEFAULT '',
                new_rel TEXT NOT NULL DEFAULT '',
                local_hardlink_path TEXT NOT NULL DEFAULT '',
                inventory_path TEXT NOT NULL DEFAULT '',
                inventory_exists INTEGER NOT NULL DEFAULT 0,
                file_size INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'planned',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (downloader_id, info_hash, file_index)
            );
            CREATE INDEX IF NOT EXISTS idx_file_mappings_media
                ON file_mappings(media_id, state, updated_at DESC);
            """
        )
        connection.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_media_items_downloader_hash
               ON media_items(downloader_id, info_hash)
               WHERE downloader_id != '' AND info_hash != ''"""
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
            "rss_tasks": "rss_tasks",
            "rss_history": "rss_history",
            "background_tasks": "background_tasks",
            "import_watches": "import_watches",
            "file_mappings": "file_mappings",
        }
        with self.connection() as connection:
            counts = {
                key: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for key, table in tables.items()
            }
            counts["torrents"] = int(connection.execute(
                "SELECT COUNT(*) FROM torrent_snapshots WHERE present = 1"
            ).fetchone()[0])
            return counts

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

    def get_media_item(self, media_id: object) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM media_items WHERE id = ?",
                (str(media_id or "").strip(),),
            ).fetchone()
        return self._decode_row(row) if row else None

    def delete_media_item(self, media_id: object) -> bool:
        identity = str(media_id or "").strip()
        if not identity:
            return False
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM file_mappings WHERE media_id = ?",
                (identity,),
            )
            cursor = connection.execute(
                "DELETE FROM media_items WHERE id = ?",
                (identity,),
            )
        return bool(cursor.rowcount)

    def list_torrents(
        self,
        downloader_id: str = "",
        view: str = "",
        keyword: str = "",
        offset: object = 0,
        limit: object = 50,
        present_only: bool = True,
    ) -> Dict[str, Any]:
        safe_offset, safe_limit = self._page(offset, limit)
        clauses: List[str] = []
        params: List[Any] = []
        if present_only:
            clauses.append("present = 1")
        if downloader_id:
            clauses.append("downloader_id = ?")
            params.append(downloader_id)
        if view == "existing":
            clauses.append("inventory_state = 'exists'")
        elif view == "pending":
            clauses.append("inventory_state != 'exists'")
        elif view == "recognized":
            clauses.append("recognition_state = 'identified'")
        elif view == "unrecognized":
            clauses.append("recognition_state = 'unidentified'")
        if keyword:
            clauses.append("(name LIKE ? OR media_title LIKE ? OR info_hash LIKE ?)")
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM torrent_snapshots {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM torrent_snapshots {where}
                    ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                [*params, safe_limit, safe_offset],
            ).fetchall()
        return self._result(rows, total, safe_offset, safe_limit)

    def get_torrent_snapshot(
        self, downloader_id: str, info_hash: str
    ) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM torrent_snapshots
                   WHERE downloader_id = ? AND info_hash = ?""",
                (downloader_id, info_hash),
            ).fetchone()
        return self._decode_row(row) if row else None

    def mark_downloader_seen(
        self,
        downloader_id: str,
        seen_hashes: List[str],
        seen_at: str,
    ) -> None:
        normalized = sorted({value for value in seen_hashes if value})
        with self.connection() as connection:
            connection.execute(
                """UPDATE torrent_snapshots
                   SET present = 0,
                       missing_since = COALESCE(missing_since, ?),
                       updated_at = ?
                   WHERE downloader_id = ?""",
                (seen_at, seen_at, downloader_id),
            )
            for start in range(0, len(normalized), 500):
                batch = normalized[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                connection.execute(
                    f"""UPDATE torrent_snapshots
                        SET present = 1, missing_since = NULL, last_seen_at = ?
                        WHERE downloader_id = ? AND info_hash IN ({placeholders})""",
                    [seen_at, downloader_id, *batch],
                )

    def mark_torrents_outside_scope(
        self,
        allowed_scope: Dict[str, List[str]],
        changed_at: str,
    ) -> int:
        normalized = {
            str(downloader or "").strip(): {
                str(category or "").strip()
                for category in categories
                if str(category or "").strip()
            }
            for downloader, categories in (allowed_scope or {}).items()
            if str(downloader or "").strip()
        }
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT downloader_id, info_hash, category, media_id
                   FROM torrent_snapshots WHERE present = 1"""
            ).fetchall()
            outside = [
                (
                    str(row["downloader_id"]),
                    str(row["info_hash"]),
                    str(row["media_id"] or ""),
                )
                for row in rows
                if str(row["category"] or "").strip()
                not in normalized.get(str(row["downloader_id"]), set())
            ]
            connection.executemany(
                """UPDATE torrent_snapshots
                   SET present = 0,
                       missing_since = COALESCE(missing_since, ?),
                       updated_at = ?
                   WHERE downloader_id = ? AND info_hash = ?""",
                [
                    (changed_at, changed_at, downloader, info_hash)
                    for downloader, info_hash, _media_id in outside
                ],
            )
            connection.executemany(
                """DELETE FROM media_items
                   WHERE id = ? AND state IN (
                       'discovered', 'identified', 'unidentified', 'existing'
                   )""",
                [(media_id,) for _downloader, _info_hash, media_id in outside if media_id],
            )
        return len(outside)

    def upsert_torrent_snapshot(self, record: Dict[str, Any]) -> None:
        fields = (
            "downloader_id", "info_hash", "name", "state", "category",
            "content_path", "progress", "size", "media_id", "source_url_masked",
            "present", "recognition_state", "inventory_state", "media_title",
            "media_type", "media_year", "tmdb_id", "season", "poster",
            "recognition_error", "recognized_at", "last_seen_at", "missing_since",
            "details_json", "updated_at",
        )
        values = []
        for field in fields:
            if field == "details_json":
                values.append(self._json_dump(record.get("details") or {}))
            else:
                values.append(record.get(field))
        placeholders = ", ".join("?" for _ in fields)
        updates = ", ".join(
            f"{field} = excluded.{field}"
            for field in fields
            if field not in {"downloader_id", "info_hash"}
        )
        with self.connection() as connection:
            connection.execute(
                f"""INSERT INTO torrent_snapshots({', '.join(fields)})
                    VALUES ({placeholders})
                    ON CONFLICT(downloader_id, info_hash) DO UPDATE SET {updates}""",
                values,
            )

    def upsert_media_item(self, record: Dict[str, Any]) -> None:
        now = record.get("updated_at") or utc_now()
        values = (
            record["id"], record["state"], record.get("media_type"),
            record.get("title") or "", record.get("source_name") or "",
            record.get("source_path") or "", record.get("downloader_id") or "",
            record.get("info_hash") or "", record.get("tmdb_id"),
            record.get("season"), record.get("category") or "",
            record.get("target_name") or "", record.get("failure_code") or "",
            record.get("failure_message") or "", int(bool(record.get("rolled_back"))),
            self._json_dump(record.get("details") or {}),
            record.get("created_at") or now, now,
        )
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO media_items(
                    id, state, media_type, title, source_name, source_path,
                    downloader_id, info_hash, tmdb_id, season, category, target_name,
                    failure_code, failure_message, rolled_back, details_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state = excluded.state,
                    media_type = excluded.media_type,
                    title = excluded.title,
                    source_name = excluded.source_name,
                    source_path = excluded.source_path,
                    downloader_id = excluded.downloader_id,
                    info_hash = excluded.info_hash,
                    tmdb_id = excluded.tmdb_id,
                    season = excluded.season,
                    category = excluded.category,
                    target_name = excluded.target_name,
                    failure_code = excluded.failure_code,
                    failure_message = excluded.failure_message,
                    rolled_back = excluded.rolled_back,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at""",
                values,
            )

    def replace_file_mappings(
        self,
        downloader_id: object,
        info_hash: object,
        records: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not downloader or not normalized_hash:
            raise ValueError("文件映射缺少下载器或 info-hash")
        now = utc_now()
        prepared = []
        for fallback_index, record in enumerate(records or []):
            try:
                file_index = int(record.get("file_index", fallback_index))
            except (TypeError, ValueError):
                file_index = fallback_index
            prepared.append((
                downloader,
                normalized_hash,
                file_index,
                str(record.get("media_id") or ""),
                str(record.get("source_relative_path") or ""),
                str(record.get("current_source_path") or ""),
                str(record.get("new_rel") or ""),
                str(record.get("local_hardlink_path") or ""),
                str(record.get("inventory_path") or ""),
                int(bool(record.get("inventory_exists"))),
                max(0, int(record.get("file_size") or 0)),
                str(record.get("state") or "planned"),
                self._json_dump(record.get("details") or {}),
                str(record.get("created_at") or now),
                now,
            ))
        with self.connection() as connection:
            connection.execute(
                "DELETE FROM file_mappings WHERE downloader_id = ? AND info_hash = ?",
                (downloader, normalized_hash),
            )
            connection.executemany(
                """INSERT INTO file_mappings(
                    downloader_id, info_hash, file_index, media_id,
                    source_relative_path, current_source_path, new_rel,
                    local_hardlink_path, inventory_path, inventory_exists,
                    file_size, state, details_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                prepared,
            )
        return self.list_file_mappings(downloader, normalized_hash)

    def list_file_mappings(
        self,
        downloader_id: object,
        info_hash: object,
    ) -> List[Dict[str, Any]]:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not downloader or not normalized_hash:
            return []
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM file_mappings
                   WHERE downloader_id = ? AND info_hash = ?
                   ORDER BY file_index""",
                (downloader, normalized_hash),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def create_background_task(self, task_id: str, task_type: str) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO background_tasks(
                    id, task_type, state, created_at, updated_at
                ) VALUES (?, ?, 'running', ?, ?)""",
                (task_id, task_type, now, now),
            )

    def update_background_task(
        self,
        task_id: str,
        *,
        current_item: Optional[str] = None,
        processed: Optional[int] = None,
        succeeded: Optional[int] = None,
        failed: Optional[int] = None,
        total: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        updates = ["updated_at = ?"]
        values: List[Any] = [utc_now()]
        fields = {
            "current_item": current_item,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "total": total,
            "error_message": error_message,
        }
        for field, value in fields.items():
            if value is not None:
                updates.append(f"{field} = ?")
                values.append(value)
        if result is not None:
            updates.append("result_json = ?")
            values.append(self._json_dump(result))
        values.append(task_id)
        with self.connection() as connection:
            connection.execute(
                f"UPDATE background_tasks SET {', '.join(updates)} WHERE id = ?",
                values,
            )

    def finish_background_task(
        self,
        task_id: str,
        state: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        error_message: str = "",
    ) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """UPDATE background_tasks
                   SET state = ?, result_json = ?, error_message = ?,
                       updated_at = ?, finished_at = ?
                   WHERE id = ?""",
                (
                    state,
                    self._json_dump(result or {}),
                    error_message,
                    now,
                    now,
                    task_id,
                ),
            )

    def get_background_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM background_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._decode_row(row) if row else None

    def latest_running_task(self, task_type: str) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM background_tasks
                   WHERE task_type = ? AND state = 'running'
                   ORDER BY created_at DESC LIMIT 1""",
                (task_type,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def recover_incomplete_tasks(self) -> int:
        now = utc_now()
        with self.connection() as connection:
            cursor = connection.execute(
                """UPDATE background_tasks
                   SET state = 'failed', error_message = '插件重启，任务已中断',
                       updated_at = ?, finished_at = ?
                   WHERE state IN ('queued', 'running')""",
                (now, now),
            )
            return int(cursor.rowcount or 0)

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

    def list_all_rss_tasks(self) -> List[Dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM rss_tasks
                   ORDER BY position ASC, created_at ASC"""
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def replace_rss_tasks(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        now = utc_now()
        with self.connection() as connection:
            existing = {
                str(row["id"]): str(row["created_at"])
                for row in connection.execute(
                    "SELECT id, created_at FROM rss_tasks"
                ).fetchall()
            }
            connection.execute("DELETE FROM rss_tasks")
            connection.executemany(
                """INSERT INTO rss_tasks(
                    id, name, enabled, position, config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        task["id"],
                        task["name"],
                        int(bool(task.get("enabled"))),
                        int(task.get("position") or 0),
                        self._json_dump(task.get("config") or {}),
                        existing.get(task["id"], now),
                        now,
                    )
                    for task in tasks
                ],
            )
        return self.list_all_rss_tasks()

    def list_rss_history(self, offset: object = 0, limit: object = 50) -> Dict[str, Any]:
        return self._list_table("rss_history", "created_at", offset, limit)

    def find_rss_source_keys(
        self,
        task_id: object,
        source_keys: Iterable[object],
    ) -> Set[str]:
        normalized_task_id = str(task_id or "").strip()
        normalized_keys = sorted({
            str(item or "").strip()
            for item in source_keys or []
            if str(item or "").strip()
        })
        if not normalized_task_id or not normalized_keys:
            return set()
        found: Set[str] = set()
        with self.connection() as connection:
            for offset in range(0, len(normalized_keys), 500):
                chunk = normalized_keys[offset:offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""SELECT source_key FROM rss_history
                        WHERE task_id = ?
                          AND status IN (
                            'queued', 'queued_warning', 'content_duplicate',
                            'existing', 'processed'
                          )
                          AND source_key IN ({placeholders})""",
                    (normalized_task_id, *chunk),
                ).fetchall()
                found.update(str(row["source_key"]) for row in rows)
        return found

    def find_rss_content_keys(self, content_keys: Iterable[object]) -> Set[str]:
        normalized_keys = sorted({
            str(item or "").strip()
            for item in content_keys or []
            if str(item or "").strip()
        })
        if not normalized_keys:
            return set()
        found: Set[str] = set()
        with self.connection() as connection:
            for offset in range(0, len(normalized_keys), 500):
                chunk = normalized_keys[offset:offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""SELECT DISTINCT content_key FROM rss_history
                        WHERE content_key IN ({placeholders})
                          AND status IN (
                            'queued', 'queued_warning', 'content_duplicate',
                            'existing', 'processed'
                          )""",
                    chunk,
                ).fetchall()
                found.update(str(row["content_key"]) for row in rows)
        return found

    def latest_rss_history_for_torrent(
        self, downloader_id: object, info_hash: object
    ) -> Optional[Dict[str, Any]]:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().casefold()
        if not normalized_hash:
            return None
        exact_key = f"{downloader}:{normalized_hash}".casefold()
        suffix = f"%:{normalized_hash}"
        payload_pattern = f'%"info_hash":"{normalized_hash}"%'
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM rss_history
                   WHERE status IN (
                       'queued', 'queued_warning', 'content_duplicate',
                       'existing', 'processed'
                     )
                     AND (
                       lower(content_key) = ?
                       OR lower(content_key) LIKE ?
                       OR lower(payload_json) LIKE ?
                     )
                   ORDER BY CASE WHEN lower(content_key) = ? THEN 0 ELSE 1 END,
                            updated_at DESC
                   LIMIT 20""",
                (exact_key, suffix, payload_pattern, exact_key),
            ).fetchall()
        for row in rows:
            item = self._decode_row(row)
            content_key = str(item.get("content_key") or "").casefold()
            payload = item.get("payload") or {}
            payload_hash = str(payload.get("info_hash") or "").casefold()
            if content_key == exact_key or content_key.endswith(f":{normalized_hash}"):
                return item
            if payload_hash == normalized_hash:
                return item
        return None

    def upsert_rss_history(self, record: Dict[str, Any]) -> None:
        now = str(record.get("updated_at") or utc_now())
        values = (
            str(record.get("task_id") or ""),
            str(record.get("source_key") or ""),
            str(record.get("content_key") or ""),
            str(record.get("title") or ""),
            str(record.get("status") or ""),
            str(record.get("reason") or ""),
            str(record.get("detail_url_masked") or ""),
            self._json_dump(record.get("payload") or {}),
            str(record.get("created_at") or now),
            now,
        )
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO rss_history(
                    task_id, source_key, content_key, title, status, reason,
                    detail_url_masked, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, source_key) DO UPDATE SET
                    content_key = excluded.content_key,
                    title = excluded.title,
                    status = excluded.status,
                    reason = excluded.reason,
                    detail_url_masked = excluded.detail_url_masked,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at""",
                values,
            )

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
        items = [SQLiteStore._decode_row(row) for row in rows]
        return {"items": items, "total": int(total), "offset": offset, "limit": limit}

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        for key in tuple(item):
            if key.endswith("_json"):
                try:
                    item[key.removesuffix("_json")] = json.loads(item[key] or "{}")
                except (TypeError, json.JSONDecodeError):
                    item[key.removesuffix("_json")] = {}
                del item[key]
        return item

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
