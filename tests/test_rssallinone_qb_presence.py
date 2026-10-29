"""Presence checks must only remove confirmed missing qB snapshots."""

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "rss_qb_presence_tests"
namespace = types.ModuleType(PACKAGE)
namespace.__path__ = [str(ROOT / "plugins.v2" / "rssallinone")]
sys.modules[PACKAGE] = namespace
database = importlib.import_module(PACKAGE + ".database")
presence = importlib.import_module(PACKAGE + ".qb_presence")


class QbPresenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = database.SQLiteStore(Path(self.temp.name) / "test.db")
        self.store.initialize()
        self.gateway = Mock(spec=["list_torrents", "torrent_dict"])
        self.gateway.torrent_dict.side_effect = dict
        self.service = presence.QbPresenceCheckService(self.store, self.gateway)

    def card(self, info_hash, downloader="qb-a", **values):
        record = {
            "downloader_id": downloader, "info_hash": info_hash,
            "name": "Same.Name", "media_title": "Film", "category": "old-category",
            "state": "pausedDL", "inventory_state": "missing", "present": 1,
            "source_url_masked": "https://tracker.test/details.php?id=1",
            "updated_at": database.utc_now(),
            **values,
        }
        fields = list(record)
        with self.store.write_connection() as connection:
            connection.execute(
                f"""INSERT INTO torrent_snapshots({', '.join(fields)})
                    VALUES ({', '.join('?' for _ in fields)})""",
                list(record.values()),
            )

    def database_records(self):
        with self.store.connection() as connection:
            tables = [
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ) if row[0] != "torrent_snapshots"
            ]
            return {
                table: [tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                for table in tables
            }

    def test_exists_never_updates_any_card_field_or_other_data(self):
        for index, state in enumerate(["pausedDL", "error", "stalledDL", "uploading"]):
            self.card(f"hash-{index}", state=state)
        before = self.store.list_pending_torrent_snapshots()
        other_before = self.database_records()
        self.gateway.list_torrents.return_value = [
            {"hash": f"HASH-{index}", "category": "changed", "name": "New.Name"}
            for index in range(4)
        ]
        result = self.service.check()
        self.assertEqual(result["existing"], 4)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(before, self.store.list_pending_torrent_snapshots())
        self.assertEqual(other_before, self.database_records())
        self.gateway.list_torrents.assert_called_once_with("qb-a")

    def test_missing_only_removes_snapshot_preserving_media_and_metadata(self):
        source = Path(self.temp.name) / "film.mkv"
        source.write_bytes(b"media content")
        media_id = "qb:qb-a:old-hash"
        self.store.upsert_media_item({
            "id": media_id, "state": "identified", "title": "Film",
            "source_path": str(source), "downloader_id": "qb-a",
            "info_hash": "old-hash", "details": {
                "source_url_masked": "https://tracker.test/details.php?id=1",
            },
        })
        self.store.replace_file_mappings("qb-a", "old-hash", [{
            "file_index": 1, "media_id": media_id,
            "current_source_path": str(source),
            "source_relative_path": "film.mkv", "file_size": source.stat().st_size,
        }])
        _, stat, key = database.file_identity(source)
        self.store.save_file_sha1(key, "a" * 40, str(source), stat.st_size)
        self.store.upsert_rss_history({
            "task_id": "rss", "source_key": "source",
            "content_key": "qb-a:old-hash", "status": "processed",
            "payload": {"downloader": "qb-a", "info_hash": "old-hash"},
        })
        self.store.schedule_qb_delete(
            task_id="rss", task_name="RSS", downloader_id="qb-a",
            info_hash="old-hash", due_at=database.utc_now(),
            source_path=str(source), delete_files=False,
        )
        self.card("old-hash", media_id=media_id)
        self.card("new-hash")
        other_before = self.database_records()
        self.gateway.list_torrents.return_value = [
            {"hash": "new-hash", "name": "Same.Name"},
        ]
        result = self.service.check()
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["existing"], 1)
        self.assertIsNone(self.store.get_torrent_snapshot("qb-a", "old-hash"))
        self.assertIsNotNone(self.store.get_torrent_snapshot("qb-a", "new-hash"))
        self.assertEqual(other_before, self.database_records())
        self.assertEqual(source.read_bytes(), b"media content")
        self.assertEqual(self.store.get_file_sha1(key), "a" * 40)

    def test_node_and_hash_are_both_required(self):
        self.card("same-hash")
        self.card("same-hash", downloader="qb-b")
        self.gateway.list_torrents.side_effect = lambda node: (
            [{"hash": "same-hash"}] if node == "qb-a" else []
        )
        result = self.service.check()
        self.assertEqual(result["existing"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertIsNotNone(self.store.get_torrent_snapshot("qb-a", "same-hash"))
        self.assertIsNone(self.store.get_torrent_snapshot("qb-b", "same-hash"))
        self.assertEqual(self.gateway.list_torrents.call_count, 2)

    def test_filter_all_pages_excludes_existing_and_hidden_snapshots(self):
        for index in range(125):
            self.card(f"hash-{index}", name=f"Chosen-{index}")
        self.card("existing", name="Chosen-existing", inventory_state="exists")
        self.card("hidden", name="Chosen-hidden", present=0)
        self.card("other-name", name="Other")
        self.card("other-node", downloader="qb-b", name="Chosen")
        self.gateway.list_torrents.return_value = []
        result = self.service.check(downloader_id="qb-a", keyword="Chosen")
        self.assertEqual(result["total"], 125)
        self.assertEqual(result["deleted"], 125)
        for node, info_hash in [
            ("qb-a", "existing"), ("qb-a", "hidden"),
            ("qb-a", "other-name"), ("qb-b", "other-node"),
        ]:
            self.assertIsNotNone(self.store.get_torrent_snapshot(node, info_hash))
        self.gateway.list_torrents.assert_called_once_with("qb-a")

    def test_failed_node_is_preserved_while_other_node_is_checked(self):
        self.card("missing")
        self.card("unknown", downloader="qb-b")
        def query(node):
            if node == "qb-b":
                raise TimeoutError("connection timeout")
            return []
        self.gateway.list_torrents.side_effect = query
        result = self.service.check()
        self.assertTrue(result["partial"])
        self.assertFalse(result["success"])
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertIsNotNone(self.store.get_torrent_snapshot("qb-b", "unknown"))

    def test_invalid_responses_never_delete_cards(self):
        self.card("missing")
        before = self.store.list_pending_torrent_snapshots()
        for response in [None, False, {}, "[]", [{}], [{"hash": ""}],
                         [{"hash": "other"}, {"hash": None}], [object()]]:
            with self.subTest(response=response):
                self.gateway.list_torrents.return_value = response
                result = self.service.check()
                self.assertEqual(result["failed"], 1)
                self.assertEqual(result["deleted"], 0)
                self.assertEqual(before, self.store.list_pending_torrent_snapshots())

    def test_card_changed_during_query_is_skipped_even_in_same_second(self):
        self.card("missing")
        def query(_node):
            with self.store.write_connection() as connection:
                connection.execute(
                    "UPDATE torrent_snapshots SET name = 'Renamed' WHERE info_hash = 'missing'"
                )
            return []
        self.gateway.list_torrents.side_effect = query
        result = self.service.check()
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(
            self.store.get_torrent_snapshot("qb-a", "missing")["name"], "Renamed"
        )

    def test_new_card_created_during_query_is_outside_original_candidates(self):
        self.card("missing")
        def query(_node):
            self.card("new-card")
            return []
        self.gateway.list_torrents.side_effect = query
        result = self.service.check()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertIsNotNone(self.store.get_torrent_snapshot("qb-a", "new-card"))

    def test_card_leaving_pending_or_deleted_during_query_is_skipped(self):
        for index, update in enumerate([
            "UPDATE torrent_snapshots SET inventory_state = 'exists'",
            "UPDATE torrent_snapshots SET present = 0",
            "DELETE FROM torrent_snapshots",
        ]):
            with self.subTest(update=update):
                info_hash = f"changing-{index}"
                self.card(info_hash)
                def query(_node):
                    with self.store.write_connection() as connection:
                        connection.execute(f"{update} WHERE info_hash = ?", (info_hash,))
                    return []
                self.gateway.list_torrents.side_effect = query
                result = self.service.check(keyword=info_hash)
                self.assertEqual(result["skipped"], 1)
                self.assertEqual(result["deleted"], 0)

    def test_no_candidates_makes_no_qb_request(self):
        result = self.service.check()
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 0)
        self.gateway.list_torrents.assert_not_called()


if __name__ == "__main__":
    unittest.main()
