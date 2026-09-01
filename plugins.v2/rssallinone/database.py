"""SQLite persistence for durable plugin state and future workflow recovery."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple


_SQLITE_WRITE_LOCK = threading.RLock()


SCHEMA_VERSION = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path_identity(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return os.path.normcase(os.path.normpath(raw))


class SQLiteStore:
    """Small repository layer with one connection per operation."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._migration_lock = threading.Lock()
        # Keep the instance attribute for compatibility while sharing the
        # actual lock across store instances in this process.
        self._write_lock = _SQLITE_WRITE_LOCK
        self._busy_timeout_ms = 10000
        self._write_retry_delays = (0.1, 0.25, 0.5, 1.0)

    def _open_connection(self) -> sqlite3.Connection:
        timeout_seconds = max(1.0, self._busy_timeout_ms / 1000)
        connection = sqlite3.connect(self.path, timeout=timeout_seconds)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        return connection

    @staticmethod
    def is_busy_error(error: BaseException) -> bool:
        if not isinstance(error, sqlite3.OperationalError):
            return False
        message = str(error or "").casefold()
        return "locked" in message or "busy" in message

    def _retry_busy(self, operation: Any) -> Any:
        delays = (0.0, *self._write_retry_delays)
        for index, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                return operation()
            except sqlite3.OperationalError as error:
                if not self.is_busy_error(error) or index + 1 >= len(delays):
                    raise
        raise RuntimeError("SQLite 写入重试状态异常")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._open_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def write_connection(self) -> Iterator[sqlite3.Connection]:
        """Serialize writes and retry transient locks from overlapping instances."""
        with self._write_lock:
            connection = self._open_connection()
            try:
                self._retry_busy(lambda: connection.execute("BEGIN IMMEDIATE"))
                yield connection
                self._retry_busy(connection.commit)
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock, self._migration_lock:
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
                        task_name TEXT NOT NULL DEFAULT '',
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

                    CREATE TABLE IF NOT EXISTS qb_delete_jobs (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL DEFAULT '',
                        task_name TEXT NOT NULL DEFAULT '',
                        downloader_id TEXT NOT NULL,
                        info_hash TEXT NOT NULL,
                        source_path TEXT NOT NULL DEFAULT '',
                        delete_files INTEGER NOT NULL DEFAULT 0,
                        due_at TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'pending',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_qb_delete_jobs_due
                        ON qb_delete_jobs(state, due_at);

                    CREATE TABLE IF NOT EXISTS hr_torrents (
                        task_id TEXT NOT NULL,
                        downloader_id TEXT NOT NULL,
                        info_hash TEXT NOT NULL,
                        torrent_id TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT '',
                        source_path TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL DEFAULT 'downloading',
                        hardlink_state TEXT NOT NULL DEFAULT 'pending',
                        downstream_state TEXT NOT NULL DEFAULT 'pending',
                        delete_files INTEGER NOT NULL DEFAULT 0,
                        safe_to_delete INTEGER NOT NULL DEFAULT 0,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT,
                        deleted_at TEXT,
                        PRIMARY KEY (task_id, downloader_id, info_hash)
                    );
                    CREATE INDEX IF NOT EXISTS idx_hr_torrents_task_state
                        ON hr_torrents(task_id, state, updated_at DESC);

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

                    CREATE TABLE IF NOT EXISTS import_batches (
                        id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        trigger_source TEXT NOT NULL DEFAULT '',
                        current_media_id TEXT NOT NULL DEFAULT '',
                        original_catchup_enabled INTEGER,
                        original_scan_enabled INTEGER,
                        succeeded INTEGER NOT NULL DEFAULT 0,
                        failed INTEGER NOT NULL DEFAULT 0,
                        risk_count INTEGER NOT NULL DEFAULT 0,
                        resume_at TEXT,
                        refresh_requested_at TEXT,
                        scan_callback_deadline TEXT,
                        error_message TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        finished_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_import_batches_state
                        ON import_batches(state, updated_at DESC);

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

                    CREATE TABLE IF NOT EXISTS emby_callback_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_id TEXT NOT NULL DEFAULT '',
                        payload_type TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        coerced_json TEXT NOT NULL DEFAULT '{}',
                        event_json TEXT NOT NULL DEFAULT '{}',
                        result_json TEXT NOT NULL DEFAULT '{}',
                        accepted INTEGER NOT NULL DEFAULT 0,
                        message TEXT NOT NULL DEFAULT '',
                        received_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_emby_callback_events_received
                        ON emby_callback_events(received_at DESC, id DESC);
                    """
                )
                self._migrate_v2(connection)
                self._migrate_v3(connection)
                self._migrate_v4(connection)
                self._migrate_v5(connection)
                self._migrate_v6(connection)
                self._migrate_v7(connection)
                self._migrate_v8(connection)
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

    @staticmethod
    def _migrate_v4(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS qb_delete_jobs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL DEFAULT '',
                task_name TEXT NOT NULL DEFAULT '',
                downloader_id TEXT NOT NULL,
                info_hash TEXT NOT NULL,
                source_path TEXT NOT NULL DEFAULT '',
                delete_files INTEGER NOT NULL DEFAULT 0,
                due_at TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_qb_delete_jobs_due
                ON qb_delete_jobs(state, due_at);
            """
        )

    @staticmethod
    def _migrate_v5(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                trigger_source TEXT NOT NULL DEFAULT '',
                current_media_id TEXT NOT NULL DEFAULT '',
                original_catchup_enabled INTEGER,
                original_scan_enabled INTEGER,
                succeeded INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                risk_count INTEGER NOT NULL DEFAULT 0,
                resume_at TEXT,
                refresh_requested_at TEXT,
                scan_callback_deadline TEXT,
                error_message TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_import_batches_state
                ON import_batches(state, updated_at DESC);
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(import_watches)").fetchall()
        }
        additions = {
            "batch_id": "TEXT NOT NULL DEFAULT ''",
            "file_index": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE import_watches ADD COLUMN {name} {definition}"
                )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_import_watches_batch_state
               ON import_watches(batch_id, state, updated_at DESC)"""
        )

    @staticmethod
    def _migrate_v6(connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(background_tasks)").fetchall()
        }
        if "task_name" not in columns:
            connection.execute(
                "ALTER TABLE background_tasks ADD COLUMN task_name TEXT NOT NULL DEFAULT ''"
            )

    @staticmethod
    def _migrate_v7(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS emby_callback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL DEFAULT '',
                payload_type TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                coerced_json TEXT NOT NULL DEFAULT '{}',
                event_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                accepted INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_emby_callback_events_received
                ON emby_callback_events(received_at DESC, id DESC);
            """
        )
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(emby_callback_events)"
            ).fetchall()
        }
        if "result_json" not in columns:
            connection.execute(
                "ALTER TABLE emby_callback_events "
                "ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}'"
            )

    @staticmethod
    def _migrate_v8(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS hr_torrents (
                task_id TEXT NOT NULL,
                downloader_id TEXT NOT NULL,
                info_hash TEXT NOT NULL,
                torrent_id TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'downloading',
                hardlink_state TEXT NOT NULL DEFAULT 'pending',
                downstream_state TEXT NOT NULL DEFAULT 'pending',
                delete_files INTEGER NOT NULL DEFAULT 0,
                safe_to_delete INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                deleted_at TEXT,
                PRIMARY KEY (task_id, downloader_id, info_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_hr_torrents_task_state
                ON hr_torrents(task_id, state, updated_at DESC);
            """
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
            "background_tasks": "background_tasks",
            "qb_delete_jobs": "qb_delete_jobs",
            "import_watches": "import_watches",
            "import_batches": "import_batches",
            "file_mappings": "file_mappings",
            "emby_callbacks": "emby_callback_events",
        }
        with self.connection() as connection:
            counts = {
                key: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for key, table in tables.items()
            }
            counts["rss_history"] = int(connection.execute(
                "SELECT COUNT(*) FROM rss_history WHERE status != 'archived'"
            ).fetchone()[0])
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
        rss_task_ids: Iterable[object] = (),
        offset: object = 0,
        limit: object = 50,
    ) -> Dict[str, Any]:
        safe_offset, safe_limit = self._page(offset, limit)
        clauses: List[str] = []
        params: List[Any] = []
        count_clauses: List[str] = []
        count_params: List[Any] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
            count_clauses.append("media_type = ?")
            count_params.append(media_type)
        normalized_task_ids = sorted({
            str(item or "").strip()
            for item in rss_task_ids or []
            if str(item or "").strip()
        })
        if normalized_task_ids:
            placeholders = ",".join("?" for _ in normalized_task_ids)
            task_clause = (
                "json_extract(details_json, '$.import_control.task_id') "
                f"IN ({placeholders})"
            )
            clauses.append(task_clause)
            params.extend(normalized_task_ids)
            count_clauses.append(task_clause)
            count_params.extend(normalized_task_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        count_where = (
            f"WHERE {' AND '.join(count_clauses)}" if count_clauses else ""
        )
        with self.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM media_items {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM media_items {where}
                    ORDER BY
                        COALESCE(NULLIF(title, ''), source_name) COLLATE NOCASE ASC,
                        CASE lower(COALESCE(
                            json_extract(details_json, '$.recognition.meta.resource_pix'),
                            json_extract(details_json, '$.meta.resource_pix'),
                            json_extract(details_json, '$.recognition.resource_pix'),
                            json_extract(details_json, '$.resource_pix'),
                            ''
                        ))
                            WHEN '480p' THEN 0
                            WHEN '576p' THEN 1
                            WHEN '720p' THEN 2
                            WHEN '1080p' THEN 3
                            WHEN '1440p' THEN 4
                            WHEN '2160p' THEN 5
                            WHEN '4k' THEN 5
                            WHEN 'uhd' THEN 5
                            ELSE 99
                        END ASC,
                        COALESCE(
                            json_extract(details_json, '$.recognition.meta.customization'),
                            json_extract(details_json, '$.meta.customization'),
                            json_extract(details_json, '$.recognition.customization'),
                            json_extract(details_json, '$.customization'),
                            ''
                        ) COLLATE NOCASE ASC,
                        source_name COLLATE NOCASE ASC,
                        id ASC
                    LIMIT ? OFFSET ?""",
                [*params, safe_limit, safe_offset],
            ).fetchall()
            state_rows = connection.execute(
                f"""SELECT state, COUNT(*) AS item_count
                    FROM media_items {count_where}
                    GROUP BY state""",
                count_params,
            ).fetchall()
        result = self._result(rows, total, safe_offset, safe_limit)
        result["state_counts"] = {
            str(row["state"] or ""): int(row["item_count"] or 0)
            for row in state_rows
            if str(row["state"] or "")
        }
        return result

    def get_media_item(self, media_id: object) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM media_items WHERE id = ?",
                (str(media_id or "").strip(),),
            ).fetchone()
        return self._decode_row(row) if row else None

    def find_media_by_source_path(self, source_path: object) -> Optional[Dict[str, Any]]:
        identity = _path_identity(source_path)
        if not identity:
            return None
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM media_items WHERE source_path != ''"
            ).fetchall()
        for row in rows:
            decoded = self._decode_row(row)
            if _path_identity(decoded.get("source_path")) == identity:
                return decoded
        return None

    def find_media_owners_by_source_paths(
        self,
        source_paths: Iterable[object],
        *,
        exclude_media_id: object = "",
    ) -> List[str]:
        identities = {
            identity for identity in (_path_identity(path) for path in source_paths)
            if identity
        }
        if not identities:
            return []
        excluded = str(exclude_media_id or "").strip()
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT DISTINCT media_id, current_source_path
                   FROM file_mappings
                   WHERE media_id != '' AND current_source_path != ''"""
            ).fetchall()
        owners = []
        for row in rows:
            media_id = str(row["media_id"] or "")
            if media_id == excluded:
                continue
            if _path_identity(row["current_source_path"]) in identities:
                owners.append(media_id)
        return sorted(set(owners))

    def delete_media_item(self, media_id: object) -> bool:
        identity = str(media_id or "").strip()
        if not identity:
            return False
        with self.write_connection() as connection:
            connection.execute(
                "DELETE FROM file_mappings WHERE media_id = ?",
                (identity,),
            )
            cursor = connection.execute(
                "DELETE FROM media_items WHERE id = ?",
                (identity,),
            )
        return bool(cursor.rowcount)

    def clear_task_records(self, task_id: object, qb_category: object = "") -> Dict[str, int]:
        """Remove qB-backed records for one task without touching local cards or qB files."""
        normalized_task = str(task_id or "").strip()
        category = str(qb_category or "").strip()
        if not normalized_task:
            return {
                "media": 0,
                "torrents": 0,
                "mappings": 0,
                "watches": 0,
                "jobs": 0,
                "history": 0,
            }
        with self.write_connection() as connection:
            media_rows = connection.execute(
                """SELECT id FROM media_items
                   WHERE json_extract(details_json, '$.import_control.task_id') = ?
                     AND (
                       json_extract(details_json, '$.source_identity.kind') = 'qb_download'
                       OR id LIKE 'qb:%'
                     )""",
                (normalized_task,),
            ).fetchall()
            media_ids = [str(row["id"]) for row in media_rows]
            torrent_rows = connection.execute(
                "SELECT downloader_id, info_hash FROM torrent_snapshots WHERE json_extract(details_json, '$.import_control.task_id') = ?"
                + (" OR category = ?" if category else ""),
                (normalized_task, category) if category else (normalized_task,),
            ).fetchall()
            mappings = 0
            watches = 0
            jobs = 0
            if media_ids:
                placeholders = ",".join("?" for _ in media_ids)
                mappings = int(connection.execute(
                    f"DELETE FROM file_mappings WHERE media_id IN ({placeholders})", media_ids
                ).rowcount or 0)
                watches = int(connection.execute(
                    f"DELETE FROM import_watches WHERE media_id IN ({placeholders})", media_ids
                ).rowcount or 0)
                connection.execute(f"DELETE FROM media_items WHERE id IN ({placeholders})", media_ids)
            if torrent_rows:
                jobs = int(connection.executemany(
                    "DELETE FROM qb_delete_jobs WHERE downloader_id = ? AND info_hash = ?",
                    [(str(row["downloader_id"]), str(row["info_hash"])) for row in torrent_rows],
                ).rowcount or 0)
                connection.executemany(
                    "DELETE FROM torrent_snapshots WHERE downloader_id = ? AND info_hash = ?",
                    [(str(row["downloader_id"]), str(row["info_hash"])) for row in torrent_rows],
                )
            history_params: List[Any] = [normalized_task]
            history_clause = (
                "task_id = ? AND json_extract(payload_json, '$.manual_source') = 1"
            )
            if torrent_rows:
                content_keys = [
                    f"{str(row['downloader_id'])}:{str(row['info_hash']).lower()}"
                    for row in torrent_rows
                ]
                placeholders = ",".join("?" for _ in content_keys)
                history_clause = (
                    f"({history_clause}) OR content_key IN ({placeholders})"
                )
                history_params.extend(content_keys)
            history = int(connection.execute(
                f"DELETE FROM rss_history WHERE {history_clause}",
                history_params,
            ).rowcount or 0)
            return {
                "media": len(media_ids),
                "torrents": len(torrent_rows),
                "mappings": mappings,
                "watches": watches,
                "jobs": jobs,
                "history": history,
            }

    def delete_completed_media_workflow(self, media_id: object) -> Dict[str, int]:
        """Remove finished operational data while retaining a compact RSS dedup key."""
        identity = str(media_id or "").strip()
        if not identity:
            return {"media": 0, "history": 0, "torrents": 0, "jobs": 0}
        with self.write_connection() as connection:
            row = connection.execute(
                "SELECT downloader_id, info_hash FROM media_items WHERE id = ?",
                (identity,),
            ).fetchone()
            if not row:
                return {"media": 0, "history": 0, "torrents": 0, "jobs": 0}
            downloader_id = str(row["downloader_id"] or "").strip()
            info_hash = str(row["info_hash"] or "").strip().lower()
            history = self._archive_rss_history_for_torrent(
                connection, downloader_id, info_hash
            )
            torrents = 0
            jobs = 0
            if downloader_id and info_hash:
                torrents = int(connection.execute(
                    """DELETE FROM torrent_snapshots
                       WHERE downloader_id = ? AND info_hash = ?""",
                    (downloader_id, info_hash),
                ).rowcount or 0)
                jobs = int(connection.execute(
                    """DELETE FROM qb_delete_jobs
                       WHERE downloader_id = ? AND info_hash = ?
                         AND state = 'succeeded'""",
                    (downloader_id, info_hash),
                ).rowcount or 0)
            connection.execute(
                "DELETE FROM import_watches WHERE media_id = ?", (identity,)
            )
            connection.execute(
                "DELETE FROM file_mappings WHERE media_id = ?", (identity,)
            )
            media = int(connection.execute(
                "DELETE FROM media_items WHERE id = ?", (identity,)
            ).rowcount or 0)
        return {
            "media": media,
            "history": history,
            "torrents": torrents,
            "jobs": jobs,
        }

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
        count_clauses: List[str] = []
        count_params: List[Any] = []
        if present_only:
            clauses.append("present = 1")
            count_clauses.append("present = 1")
        if downloader_id:
            clauses.append("downloader_id = ?")
            params.append(downloader_id)
            count_clauses.append("downloader_id = ?")
            count_params.append(downloader_id)
        if view == "existing":
            clauses.append("inventory_state = 'exists'")
        elif view == "pending":
            clauses.append("inventory_state != 'exists'")
        elif view == "recognized":
            clauses.append("recognition_state = 'identified'")
        elif view == "unrecognized":
            clauses.append("recognition_state = 'unidentified'")
        if keyword:
            keyword_clause = "(name LIKE ? OR media_title LIKE ? OR info_hash LIKE ?)"
            clauses.append(keyword_clause)
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern, pattern])
            count_clauses.append(keyword_clause)
            count_params.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        count_where = (
            f"WHERE {' AND '.join(count_clauses)}" if count_clauses else ""
        )
        with self.connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM torrent_snapshots {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM torrent_snapshots {where}
                    ORDER BY name COLLATE NOCASE ASC,
                             downloader_id COLLATE NOCASE ASC,
                             info_hash ASC
                    LIMIT ? OFFSET ?""",
                [*params, safe_limit, safe_offset],
            ).fetchall()
            view_counts = connection.execute(
                f"""SELECT
                        SUM(CASE WHEN inventory_state = 'exists' THEN 1 ELSE 0 END)
                            AS existing_count,
                        SUM(CASE WHEN inventory_state != 'exists' THEN 1 ELSE 0 END)
                            AS pending_count
                    FROM torrent_snapshots {count_where}""",
                count_params,
            ).fetchone()
        result = self._result(rows, total, safe_offset, safe_limit)
        result["view_counts"] = {
            "existing": int(view_counts["existing_count"] or 0),
            "pending": int(view_counts["pending_count"] or 0),
        }
        return result

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
        with self.write_connection() as connection:
            if normalized:
                placeholders = ",".join("?" for _ in normalized)
                connection.execute(
                    f"""DELETE FROM torrent_snapshots
                        WHERE downloader_id = ?
                          AND info_hash NOT IN ({placeholders})""",
                    [downloader_id, *normalized],
                )
            else:
                connection.execute(
                    "DELETE FROM torrent_snapshots WHERE downloader_id = ?",
                    (downloader_id,),
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
        with self.write_connection() as connection:
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
                """DELETE FROM torrent_snapshots
                   WHERE downloader_id = ? AND info_hash = ?""",
                [
                    (downloader, info_hash)
                    for downloader, info_hash, _media_id in outside
                ],
            )
            connection.executemany(
                "DELETE FROM file_mappings WHERE media_id = ?",
                [(media_id,) for _downloader, _info_hash, media_id in outside if media_id],
            )
            connection.executemany(
                """DELETE FROM media_items
                   WHERE id = ? AND state IN (
                       'discovered', 'identified', 'unidentified', 'existing'
                   )""",
                [(media_id,) for _downloader, _info_hash, media_id in outside if media_id],
            )
        return len(outside)

    def delete_torrent_snapshot(
        self, downloader_id: object, info_hash: object
    ) -> bool:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not downloader or not normalized_hash:
            return False
        with self.write_connection() as connection:
            cursor = connection.execute(
                """DELETE FROM torrent_snapshots
                   WHERE downloader_id = ? AND info_hash = ?""",
                (downloader, normalized_hash),
            )
        return bool(cursor.rowcount)

    def upsert_hr_torrent(self, record: Dict[str, Any]) -> None:
        task_id = str(record.get("task_id") or "").strip()
        downloader = str(record.get("downloader_id") or "").strip()
        info_hash = str(record.get("info_hash") or "").strip().lower()
        torrent_id = str(record.get("torrent_id") or "").strip()
        if not task_id or not downloader or not info_hash or not torrent_id.isdigit():
            raise ValueError("HR记录缺少任务、下载器、info-hash或torrent_id")
        now = str(record.get("updated_at") or utc_now())
        with self.write_connection() as connection:
            connection.execute(
                """INSERT INTO hr_torrents(
                    task_id, downloader_id, info_hash, torrent_id, category,
                    source_path, state, hardlink_state, downstream_state,
                    delete_files, safe_to_delete, details_json, created_at,
                    updated_at, completed_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, downloader_id, info_hash) DO UPDATE SET
                    torrent_id = excluded.torrent_id,
                    category = excluded.category,
                    source_path = CASE
                        WHEN excluded.source_path != '' THEN excluded.source_path
                        ELSE hr_torrents.source_path END,
                    state = excluded.state,
                    hardlink_state = excluded.hardlink_state,
                    downstream_state = excluded.downstream_state,
                    delete_files = excluded.delete_files,
                    safe_to_delete = excluded.safe_to_delete,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at,
                    completed_at = COALESCE(excluded.completed_at, hr_torrents.completed_at),
                    deleted_at = COALESCE(excluded.deleted_at, hr_torrents.deleted_at)""",
                (
                    task_id, downloader, info_hash, torrent_id,
                    str(record.get("category") or "").strip(),
                    str(record.get("source_path") or "").strip(),
                    str(record.get("state") or "downloading").strip(),
                    str(record.get("hardlink_state") or "pending").strip(),
                    str(record.get("downstream_state") or "pending").strip(),
                    int(bool(record.get("delete_files"))),
                    int(bool(record.get("safe_to_delete"))),
                    self._json_dump(record.get("details") or {}),
                    str(record.get("created_at") or now), now,
                    record.get("completed_at"), record.get("deleted_at"),
                ),
            )

    def get_hr_torrent(
        self, task_id: object, downloader_id: object, info_hash: object
    ) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM hr_torrents
                   WHERE task_id = ? AND downloader_id = ? AND info_hash = ?""",
                (
                    str(task_id or "").strip(),
                    str(downloader_id or "").strip(),
                    str(info_hash or "").strip().lower(),
                ),
            ).fetchone()
        return self._decode_row(row) if row else None

    def list_hr_torrents_for_task(self, task_id: object) -> List[Dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM hr_torrents
                   WHERE task_id = ? AND state NOT IN ('deleted', 'missing')
                   ORDER BY created_at ASC""",
                (str(task_id or "").strip(),),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def update_hr_torrent(
        self,
        task_id: object,
        downloader_id: object,
        info_hash: object,
        **changes: Any,
    ) -> bool:
        current = self.get_hr_torrent(task_id, downloader_id, info_hash)
        if not current:
            return False
        current.update(changes)
        current["updated_at"] = utc_now()
        self.upsert_hr_torrent(current)
        return True

    def clear_card_data(self) -> Dict[str, int]:
        with self.write_connection() as connection:
            counts = {
                "torrents": int(connection.execute(
                    "SELECT COUNT(*) FROM torrent_snapshots"
                ).fetchone()[0]),
                "media": int(connection.execute(
                    "SELECT COUNT(*) FROM media_items"
                ).fetchone()[0]),
                "file_mappings": int(connection.execute(
                    "SELECT COUNT(*) FROM file_mappings"
                ).fetchone()[0]),
                "import_watches": int(connection.execute(
                    "SELECT COUNT(*) FROM import_watches"
                ).fetchone()[0]),
                "import_batches": int(connection.execute(
                    "SELECT COUNT(*) FROM import_batches"
                ).fetchone()[0]),
                "qb_delete_jobs": int(connection.execute(
                    "SELECT COUNT(*) FROM qb_delete_jobs"
                ).fetchone()[0]),
                "completion_markers": 0,
            }
            connection.execute("DELETE FROM torrent_snapshots")
            connection.execute("DELETE FROM file_mappings")
            connection.execute("DELETE FROM import_watches")
            connection.execute("DELETE FROM import_batches")
            connection.execute("DELETE FROM media_items")
            connection.execute("DELETE FROM qb_delete_jobs")
            history_rows = connection.execute(
                "SELECT id, status, payload_json FROM rss_history"
            ).fetchall()
            for row in history_rows:
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not payload.get("completion_processed"):
                    continue
                for key in (
                    "completion_processed",
                    "completion_processed_at",
                    "imported_to_library",
                    "realtime_hardlink",
                    "qb_delete",
                ):
                    payload.pop(key, None)
                connection.execute(
                    """UPDATE rss_history
                       SET status = ?, reason = '', payload_json = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        "queued" if str(row["status"] or "") == "processed"
                        else str(row["status"] or ""),
                        self._json_dump(payload),
                        utc_now(),
                        int(row["id"]),
                    ),
                )
                counts["completion_markers"] += 1
        return counts

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
        with self.write_connection() as connection:
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
        with self.write_connection() as connection:
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
        with self.write_connection() as connection:
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

    def next_media_in_state(self, state: object) -> Optional[Dict[str, Any]]:
        normalized = str(state or "").strip()
        if not normalized:
            return None
        with self.connection() as connection:
            row = connection.execute(
                """SELECT * FROM media_items
                   WHERE state = ?
                   ORDER BY created_at ASC, id ASC
                   LIMIT 1""",
                (normalized,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def count_media_states(self, states: Iterable[object]) -> int:
        values = [str(value or "").strip() for value in states or []]
        values = [value for value in values if value]
        if not values:
            return 0
        placeholders = ",".join("?" for _ in values)
        with self.connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM media_items WHERE state IN ({placeholders})",
                values,
            ).fetchone()
        return int(row[0] or 0)

    def upsert_import_batch(self, record: Dict[str, Any]) -> None:
        now = str(record.get("updated_at") or utc_now())
        values = (
            str(record.get("id") or ""),
            str(record.get("state") or ""),
            str(record.get("trigger_source") or ""),
            str(record.get("current_media_id") or ""),
            None if record.get("original_catchup_enabled") is None
            else int(bool(record.get("original_catchup_enabled"))),
            None if record.get("original_scan_enabled") is None
            else int(bool(record.get("original_scan_enabled"))),
            max(0, int(record.get("succeeded") or 0)),
            max(0, int(record.get("failed") or 0)),
            max(0, int(record.get("risk_count") or 0)),
            record.get("resume_at"),
            record.get("refresh_requested_at"),
            record.get("scan_callback_deadline"),
            str(record.get("error_message") or ""),
            self._json_dump(record.get("details") or {}),
            str(record.get("created_at") or now),
            now,
            record.get("finished_at"),
        )
        with self.write_connection() as connection:
            connection.execute(
                """INSERT INTO import_batches(
                    id, state, trigger_source, current_media_id,
                    original_catchup_enabled, original_scan_enabled,
                    succeeded, failed, risk_count, resume_at,
                    refresh_requested_at, scan_callback_deadline,
                    error_message, details_json, created_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state = excluded.state,
                    trigger_source = excluded.trigger_source,
                    current_media_id = excluded.current_media_id,
                    original_catchup_enabled = excluded.original_catchup_enabled,
                    original_scan_enabled = excluded.original_scan_enabled,
                    succeeded = excluded.succeeded,
                    failed = excluded.failed,
                    risk_count = excluded.risk_count,
                    resume_at = excluded.resume_at,
                    refresh_requested_at = excluded.refresh_requested_at,
                    scan_callback_deadline = excluded.scan_callback_deadline,
                    error_message = excluded.error_message,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at,
                    finished_at = excluded.finished_at""",
                values,
            )

    def get_import_batch(self, batch_id: object) -> Optional[Dict[str, Any]]:
        identity = str(batch_id or "").strip()
        if not identity:
            return None
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM import_batches WHERE id = ?", (identity,)
            ).fetchone()
        return self._decode_row(row) if row else None

    def latest_active_import_batch(self) -> Optional[Dict[str, Any]]:
        terminal = ("completed", "failed", "cancelled")
        placeholders = ",".join("?" for _ in terminal)
        with self.connection() as connection:
            row = connection.execute(
                f"""SELECT * FROM import_batches
                    WHERE state NOT IN ({placeholders})
                    ORDER BY created_at DESC LIMIT 1""",
                terminal,
            ).fetchone()
        return self._decode_row(row) if row else None

    def upsert_import_watch(self, record: Dict[str, Any]) -> None:
        now = str(record.get("updated_at") or utc_now())
        values = (
            str(record.get("id") or ""),
            str(record.get("media_id") or ""),
            str(record.get("state") or "waiting_task"),
            str(record.get("local_hardlink_path") or ""),
            str(record.get("expected_cd2_dest_path") or ""),
            str(record.get("expected_mp_library_path") or ""),
            str(record.get("cd2_key") or ""),
            max(0, int(record.get("file_size") or 0)),
            max(0, int(record.get("transferred_bytes") or 0)),
            self._json_dump(record.get("details") or {}),
            str(record.get("created_at") or now),
            now,
            str(record.get("batch_id") or ""),
            max(0, int(record.get("file_index") or 0)),
        )
        with self.write_connection() as connection:
            connection.execute(
                """INSERT INTO import_watches(
                    id, media_id, state, local_hardlink_path,
                    expected_cd2_dest_path, expected_mp_library_path,
                    cd2_key, file_size, transferred_bytes, details_json,
                    created_at, updated_at, batch_id, file_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    media_id = excluded.media_id,
                    state = excluded.state,
                    local_hardlink_path = excluded.local_hardlink_path,
                    expected_cd2_dest_path = excluded.expected_cd2_dest_path,
                    expected_mp_library_path = excluded.expected_mp_library_path,
                    cd2_key = excluded.cd2_key,
                    file_size = excluded.file_size,
                    transferred_bytes = excluded.transferred_bytes,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at,
                    batch_id = excluded.batch_id,
                    file_index = excluded.file_index""",
                values,
            )

    def list_import_watches(
        self,
        *,
        batch_id: object = "",
        media_id: object = "",
        states: Iterable[object] = (),
    ) -> List[Dict[str, Any]]:
        clauses = []
        values: List[Any] = []
        if str(batch_id or "").strip():
            clauses.append("batch_id = ?")
            values.append(str(batch_id).strip())
        if str(media_id or "").strip():
            clauses.append("media_id = ?")
            values.append(str(media_id).strip())
        normalized_states = [str(value or "").strip() for value in states or []]
        normalized_states = [value for value in normalized_states if value]
        if normalized_states:
            clauses.append(
                f"state IN ({','.join('?' for _ in normalized_states)})"
            )
            values.extend(normalized_states)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM import_watches {where}
                    ORDER BY created_at ASC, file_index ASC""",
                values,
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def delete_import_watches(self, *, batch_id: object = "", media_id: object = "") -> int:
        clauses = []
        values = []
        if str(batch_id or "").strip():
            clauses.append("batch_id = ?")
            values.append(str(batch_id).strip())
        if str(media_id or "").strip():
            clauses.append("media_id = ?")
            values.append(str(media_id).strip())
        if not clauses:
            return 0
        with self.write_connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM import_watches WHERE {' AND '.join(clauses)}", values
            )
        return int(cursor.rowcount or 0)

    def schedule_qb_delete(
        self,
        *,
        task_id: object,
        task_name: object,
        downloader_id: object,
        info_hash: object,
        source_path: object,
        delete_files: bool,
        due_at: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        due = str(due_at or "").strip()
        if not downloader or not normalized_hash or not due:
            raise ValueError("qB 延时删除任务缺少下载器、info-hash 或到期时间")
        identity = f"{downloader}:{normalized_hash}"
        now = utc_now()
        with self.write_connection() as connection:
            connection.execute(
                """INSERT INTO qb_delete_jobs(
                    id, task_id, task_name, downloader_id, info_hash,
                    source_path, delete_files, due_at, state, attempts,
                    last_error, details_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, '', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_id = excluded.task_id,
                    task_name = excluded.task_name,
                    source_path = excluded.source_path,
                    delete_files = excluded.delete_files,
                    due_at = CASE
                        WHEN qb_delete_jobs.state = 'succeeded'
                            THEN qb_delete_jobs.due_at
                        WHEN qb_delete_jobs.due_at < excluded.due_at
                            THEN qb_delete_jobs.due_at
                        ELSE excluded.due_at
                    END,
                    state = CASE
                        WHEN qb_delete_jobs.state = 'succeeded'
                            THEN qb_delete_jobs.state
                        ELSE 'pending'
                    END,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at""",
                (
                    identity,
                    str(task_id or "").strip(),
                    str(task_name or "").strip(),
                    downloader,
                    normalized_hash,
                    str(source_path or "").strip(),
                    int(bool(delete_files)),
                    due,
                    self._json_dump(details or {}),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM qb_delete_jobs WHERE id = ?", (identity,)
            ).fetchone()
        return self._decode_row(row)

    def claim_due_qb_delete_jobs(
        self, now: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        current = str(now or utc_now())
        safe_limit = max(1, min(int(limit or 20), 100))
        with self.write_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM qb_delete_jobs
                   WHERE state = 'pending' AND due_at <= ?
                   ORDER BY due_at ASC LIMIT ?""",
                (current, safe_limit),
            ).fetchall()
            connection.executemany(
                """UPDATE qb_delete_jobs
                   SET state = 'running', updated_at = ? WHERE id = ?""",
                [(current, str(row["id"])) for row in rows],
            )
        return [self._decode_row(row) for row in rows]

    def finish_qb_delete_job(
        self,
        job_id: object,
        *,
        success: bool,
        error: str = "",
        retry_at: str = "",
    ) -> None:
        identity = str(job_id or "").strip()
        if not identity:
            return
        now = utc_now()
        with self.write_connection() as connection:
            if success:
                connection.execute(
                    """UPDATE qb_delete_jobs
                       SET state = 'succeeded', last_error = '', updated_at = ?
                       WHERE id = ?""",
                    (now, identity),
                )
            else:
                connection.execute(
                    """UPDATE qb_delete_jobs
                       SET state = 'pending', attempts = attempts + 1,
                           last_error = ?, due_at = ?, updated_at = ?
                       WHERE id = ?""",
                    (str(error or "")[:500], str(retry_at or now), now, identity),
                )

    def mark_qb_delete_job_needs_review(
        self, job_id: object, *, error: str
    ) -> None:
        identity = str(job_id or "").strip()
        if not identity:
            return
        with self.write_connection() as connection:
            connection.execute(
                """UPDATE qb_delete_jobs
                   SET state = 'needs_review', attempts = attempts + 1,
                       last_error = ?, updated_at = ?
                   WHERE id = ?""",
                (str(error or "")[:500], utc_now(), identity),
            )

    def delete_qb_delete_job(self, job_id: object) -> bool:
        identity = str(job_id or "").strip()
        if not identity:
            return False
        with self.write_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM qb_delete_jobs WHERE id = ?", (identity,)
            )
        return bool(cursor.rowcount)

    def delete_qb_delete_jobs_for_torrent(
        self, downloader_id: object, info_hash: object
    ) -> int:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not downloader or not normalized_hash:
            return 0
        with self.write_connection() as connection:
            cursor = connection.execute(
                """DELETE FROM qb_delete_jobs
                   WHERE downloader_id = ? AND info_hash = ?""",
                (downloader, normalized_hash),
            )
        return int(cursor.rowcount or 0)

    def cleanup_completed_qb_delete_jobs(self) -> int:
        with self.write_connection() as connection:
            rows = connection.execute(
                """SELECT id, downloader_id, info_hash FROM qb_delete_jobs
                   WHERE state = 'succeeded'"""
            ).fetchall()
            for row in rows:
                downloader_id = str(row["downloader_id"] or "").strip()
                info_hash = str(row["info_hash"] or "").strip().lower()
                self._archive_rss_history_for_torrent(
                    connection, downloader_id, info_hash
                )
                connection.execute(
                    """DELETE FROM torrent_snapshots
                       WHERE downloader_id = ? AND info_hash = ?""",
                    (downloader_id, info_hash),
                )
            if rows:
                connection.executemany(
                    "DELETE FROM qb_delete_jobs WHERE id = ?",
                    [(str(row["id"]),) for row in rows],
                )
        return len(rows)

    def list_qb_delete_jobs(self) -> List[Dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM qb_delete_jobs ORDER BY due_at DESC"
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def create_background_task(
        self,
        task_id: str,
        task_type: str,
        *,
        task_name: str = "",
        state: str = "running",
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = utc_now()
        with self.write_connection() as connection:
            connection.execute(
                """INSERT INTO background_tasks(
                    id, task_type, task_name, state, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    task_type,
                    str(task_name or "").strip(),
                    state,
                    self._json_dump(result or {}),
                    now,
                    now,
                ),
            )

    def start_background_task(self, task_id: str) -> bool:
        with self.write_connection() as connection:
            cursor = connection.execute(
                """UPDATE background_tasks
                   SET state = 'running', updated_at = ?
                   WHERE id = ? AND state = 'queued'""",
                (utc_now(), str(task_id or "").strip()),
            )
        return bool(cursor.rowcount)

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
        with self.write_connection() as connection:
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
        with self.write_connection() as connection:
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

    def recover_incomplete_tasks(
        self,
        preserve_queued_types: Optional[Iterable[str]] = None,
    ) -> int:
        now = utc_now()
        preserved = sorted({
            str(item or "").strip()
            for item in (preserve_queued_types or [])
            if str(item or "").strip()
        })
        with self.write_connection() as connection:
            params: List[Any] = [now, now]
            if preserved:
                placeholders = ",".join("?" for _ in preserved)
                queued_clause = (
                    f" OR (state = 'queued' AND task_type NOT IN ({placeholders}))"
                )
                params.extend(preserved)
                state_clause = "state = 'running'" + queued_clause
            else:
                state_clause = "state IN ('queued', 'running')"
            cursor = connection.execute(
                """UPDATE background_tasks
                   SET state = 'failed', error_message = '插件重启，任务已中断',
                       updated_at = ?, finished_at = ?
                   WHERE """ + state_clause,
                params,
            )
            return int(cursor.rowcount or 0)

    def list_background_tasks_by_state(
        self,
        task_type: str,
        states: Iterable[str],
        *,
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        normalized_states = sorted({
            str(item or "").strip()
            for item in states or []
            if str(item or "").strip()
        })
        if not normalized_states:
            return []
        placeholders = ",".join("?" for _ in normalized_states)
        order = "ASC" if ascending else "DESC"
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM background_tasks
                    WHERE task_type = ? AND state IN ({placeholders})
                    ORDER BY created_at {order}, id {order}""",
                (str(task_type or "").strip(), *normalized_states),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

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
        with self.write_connection() as connection:
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
        safe_offset, safe_limit = self._page(offset, limit)
        with self.connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM rss_history WHERE status != 'archived'"
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT * FROM rss_history
                   WHERE status != 'archived'
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (safe_limit, safe_offset),
            ).fetchall()
        return self._result(rows, total, safe_offset, safe_limit)


    def list_all_rss_history(self) -> List[Dict[str, Any]]:
        """Get all RSS history records (no pagination, no archived)."""
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM rss_history WHERE status != 'archived' ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode_row(row) for row in rows]
    def list_rss_history_for_task(self, task_id: object) -> List[Dict[str, Any]]:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return []
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM rss_history"
                " WHERE task_id = ?"
                " AND status != 'archived'"
                " ORDER BY updated_at DESC",
                (normalized_task_id,),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

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
                            'existing', 'processed', 'archived'
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
                            'existing', 'processed', 'archived'
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

    def mark_rss_torrent_completed(
        self,
        history: Dict[str, Any],
        *,
        downloader_id: object,
        info_hash: object,
        imported: bool,
        realtime_hardlink: Optional[Dict[str, Any]] = None,
        qb_delete: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not history:
            return
        payload = dict(history.get("payload") or {})
        payload.update({
            "downloader": str(downloader_id or "").strip(),
            "info_hash": str(info_hash or "").strip().lower(),
            "completion_processed": True,
            "completion_processed_at": utc_now(),
            "imported_to_library": bool(imported),
        })
        if realtime_hardlink:
            payload["realtime_hardlink"] = realtime_hardlink
        if qb_delete:
            payload["qb_delete"] = qb_delete
        realtime_state = str(
            (payload.get("realtime_hardlink") or {}).get("state") or ""
        )
        realtime_error = str(
            (payload.get("realtime_hardlink") or {}).get("error") or ""
        ).strip()
        if realtime_state == "linked":
            reason = "下载完成，已创建实时硬链接"
            if imported:
                reason += "并转入入库管理"
        elif realtime_state == "failed":
            reason = "下载完成，实时硬链接失败"
            if realtime_error:
                reason += f"：{realtime_error}"
        else:
            reason = "下载完成，已转入入库管理" if imported else "下载完成，任务未启用入库"
        self.upsert_rss_history({
            **history,
            "status": "processed",
            "reason": reason,
            "payload": payload,
            "updated_at": utc_now(),
        })

    def reopen_rss_torrent(
        self,
        history: Dict[str, Any],
        *,
        downloader_id: object,
        info_hash: object,
    ) -> None:
        """Undo a stale completion transition when qB is explicitly incomplete."""

        if not history:
            return
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        payload = dict(history.get("payload") or {})
        for key in (
            "completion_processed",
            "completion_processed_at",
            "imported_to_library",
            "qb_delete",
        ):
            payload.pop(key, None)
        payload.update({
            "downloader": downloader,
            "info_hash": normalized_hash,
        })
        self.upsert_rss_history({
            **history,
            "status": "queued",
            "reason": "qB 当前仍未完成，已恢复到 QB 管理",
            "payload": payload,
            "updated_at": utc_now(),
        })
        self.delete_qb_delete_jobs_for_torrent(downloader, normalized_hash)

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
        with self.write_connection() as connection:
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

    def archive_rss_history_for_torrent(
        self, downloader_id: object, info_hash: object
    ) -> int:
        downloader = str(downloader_id or "").strip()
        normalized_hash = str(info_hash or "").strip().lower()
        if not normalized_hash:
            return 0
        with self.write_connection() as connection:
            return self._archive_rss_history_for_torrent(
                connection, downloader, normalized_hash
            )

    def _archive_rss_history_for_torrent(
        self,
        connection: sqlite3.Connection,
        downloader_id: str,
        info_hash: str,
    ) -> int:
        normalized_hash = str(info_hash or "").strip().lower()
        if not normalized_hash:
            return 0
        exact_key = f"{str(downloader_id or '').strip()}:{normalized_hash}".lower()
        rows = connection.execute(
            """SELECT id, task_id, source_key, content_key, payload_json
               FROM rss_history
               WHERE status != 'archived'
                 AND (
                   lower(content_key) = ?
                   OR lower(content_key) LIKE ?
                   OR lower(COALESCE(json_extract(payload_json, '$.info_hash'), '')) = ?
                 )""",
            (exact_key, f"%:{normalized_hash}", normalized_hash),
        ).fetchall()
        if not rows:
            return 0
        now = utc_now()
        task_ids = set()
        for row in rows:
            task_ids.add(str(row["task_id"] or ""))
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            compact_payload = {
                "downloader": str(
                    payload.get("downloader") or downloader_id or ""
                ).strip(),
                "info_hash": normalized_hash,
                "dedup_archived": True,
            }
            connection.execute(
                """UPDATE rss_history
                   SET status = 'archived', title = '', reason = '',
                       detail_url_masked = '', payload_json = ?, updated_at = ?
                   WHERE id = ?""",
                (self._json_dump(compact_payload), now, int(row["id"])),
            )
        for task_id in task_ids:
            stale = connection.execute(
                """SELECT id FROM rss_history
                   WHERE task_id = ? AND status = 'archived'
                   ORDER BY updated_at DESC, id DESC LIMIT -1 OFFSET 1000""",
                (task_id,),
            ).fetchall()
            if stale:
                connection.executemany(
                    "DELETE FROM rss_history WHERE id = ?",
                    [(int(row["id"]),) for row in stale],
                )
        return len(rows)

    def list_background_tasks(self, offset: object = 0, limit: object = 50) -> Dict[str, Any]:
        return self._list_table("background_tasks", "updated_at", offset, limit)

    def clear_background_tasks(self) -> Dict[str, int]:
        with self.write_connection() as connection:
            running = int(connection.execute(
                """SELECT COUNT(*) FROM background_tasks
                   WHERE state IN ('queued', 'running')"""
            ).fetchone()[0])
            deleted = int(connection.execute(
                """DELETE FROM background_tasks
                   WHERE state NOT IN ('queued', 'running')"""
            ).rowcount or 0)
        return {"deleted": deleted, "running": running}

    def record_emby_callback_event(
        self,
        record: Dict[str, Any],
        *,
        keep: int = 50,
    ) -> int:
        received_at = str(record.get("received_at") or utc_now())
        with self.write_connection() as connection:
            cursor = connection.execute(
                """INSERT INTO emby_callback_events(
                    batch_id, payload_type, payload_json, coerced_json,
                    event_json, result_json, accepted, message,
                    received_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(record.get("batch_id") or ""),
                    str(record.get("payload_type") or ""),
                    self._json_dump(record.get("payload") or {}),
                    self._json_dump(record.get("coerced") or {}),
                    self._json_dump(record.get("event") or {}),
                    self._json_dump(record.get("result") or {}),
                    int(bool(record.get("accepted"))),
                    str(record.get("message") or ""),
                    received_at,
                    str(record.get("created_at") or received_at),
                ),
            )
            retained = max(1, min(200, int(keep or 50)))
            connection.execute(
                """DELETE FROM emby_callback_events
                   WHERE id NOT IN (
                       SELECT id FROM emby_callback_events
                       ORDER BY id DESC LIMIT ?
                   )""",
                (retained,),
            )
            return int(cursor.lastrowid)

    def list_emby_callback_events(
        self,
        offset: object = 0,
        limit: object = 50,
    ) -> Dict[str, Any]:
        return self._list_table("emby_callback_events", "id", offset, limit)

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
