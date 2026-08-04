"""Read-only RSS/Atom parsing, filtering, deduplication, and masking tests."""

import hashlib
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_rss_feed_tests"


def load_package_module(name: str):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


database = load_package_module("database")
rss_feed = load_package_module("rss_feed")


class RssPreviewServiceTest(unittest.TestCase):
    def test_rss_entries_are_filtered_deduplicated_and_masked(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>PT Feed</title>
          <item>
            <title>Movie.One.2026.REMUX</title>
            <link>https://pt.example/details.php?id=123&amp;token=detail-secret</link>
            <guid isPermaLink="false">opaque-one</guid>
            <pubDate>Tue, 04 Aug 2026 08:00:00 GMT</pubDate>
            <enclosure url="https://pt.example/download.php?passkey=feed-secret&amp;id=123" type="application/x-bittorrent" />
          </item>
          <item>
            <title>Movie.Two.2026.WEB-DL</title>
            <link>https://pt.example/details.php?id=124</link>
            <enclosure url="https://pt.example/download.php?id=124&amp;authkey=hidden" type="application/x-bittorrent" />
          </item>
          <item>
            <title>Movie.Three.2026.REMUX</title>
            <link>https://pt.example/details.php?id=125</link>
          </item>
          <item>
            <title>Movie.One.Duplicate.2026.REMUX</title>
            <link>https://pt.example/details.php?id=123</link>
            <enclosure url="https://pt.example/download.php?id=123&amp;passkey=changed" type="application/x-bittorrent" />
          </item>
        </channel></rss>"""

        service = rss_feed.RssPreviewService(
            fetcher=lambda _url: rss_feed.FetchResult(
                body=xml,
                final_url="https://pt.example/rss.php?rsskey=redirect-secret",
                content_type="application/rss+xml",
            )
        )
        result = service.run({
            "id": "task-a",
            "name": "REMUX",
            "config": {
                "rss_url": "https://pt.example/rss.php?passkey=request-secret",
                "name_contains": "remux",
            },
        })

        self.assertEqual(result["feed"]["title"], "PT Feed")
        self.assertEqual(result["counts"]["total"], 4)
        self.assertEqual(result["counts"]["ready"], 1)
        self.assertEqual(result["counts"]["filtered"], 1)
        self.assertEqual(result["counts"]["missing_enclosure"], 1)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(
            [item["status"] for item in result["items"]],
            ["ready", "filtered", "missing_enclosure", "duplicate"],
        )
        first = result["items"][0]
        self.assertEqual(first["torrent_id"], "123")
        self.assertEqual(first["identity_type"], "torrent_id")
        self.assertEqual(
            first["source_key"],
            hashlib.sha256(b"task-atorrent_id:123").hexdigest(),
        )
        serialized = repr(result)
        for secret in (
            "request-secret",
            "redirect-secret",
            "detail-secret",
            "feed-secret",
            "hidden",
            "changed",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("passkey=***", first["enclosure_url_masked"])
        self.assertIn("token=***", first["detail_url_masked"])

    def test_atom_opaque_guid_and_existing_history_are_supported(self) -> None:
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Atom PT</title>
          <entry>
            <title>Show.S01E01.2160p</title>
            <id>release-guid-001</id>
            <updated>2026-08-04T08:00:00Z</updated>
            <link rel="alternate" href="https://pt.example/release/one" />
            <link rel="enclosure" type="application/x-bittorrent" href="https://pt.example/torrent/one?signature=secret" />
          </entry>
        </feed>"""
        expected_key = hashlib.sha256(
            b"atom-taskguid:release-guid-001"
        ).hexdigest()
        service = rss_feed.RssPreviewService(
            fetcher=lambda _url: rss_feed.FetchResult(
                body=xml,
                final_url="https://pt.example/atom",
            ),
            existing_keys=lambda task_id, keys: (
                [expected_key] if task_id == "atom-task" and expected_key in keys else []
            ),
        )
        result = service.run({
            "id": "atom-task",
            "name": "Atom",
            "config": {"rss_url": "https://pt.example/atom"},
        })

        self.assertEqual(result["feed"]["type"], "atom")
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(result["items"][0]["identity_type"], "opaque_guid")
        self.assertEqual(result["items"][0]["source_key"], expected_key)
        self.assertNotIn("secret", repr(result))

    def test_invalid_url_and_malformed_xml_fail_safely(self) -> None:
        service = rss_feed.RssPreviewService(
            fetcher=lambda _url: rss_feed.FetchResult(
                body=b"<rss><broken>",
                final_url="https://pt.example/rss",
            )
        )
        with self.assertRaisesRegex(rss_feed.RssFeedError, "HTTP 或 HTTPS"):
            service.run({"id": "bad", "config": {"rss_url": "file:///tmp/rss"}})
        with self.assertRaisesRegex(rss_feed.RssFeedError, "XML 解析失败"):
            service.run({
                "id": "bad",
                "config": {"rss_url": "https://pt.example/rss"},
            })

    def test_non_torrent_enclosure_is_not_eligible(self) -> None:
        xml = b"""<rss><channel><item>
          <title>Poster only</title>
          <guid>poster-guid</guid>
          <enclosure url="https://pt.example/poster.jpg?token=secret" type="image/jpeg" />
        </item></channel></rss>"""
        service = rss_feed.RssPreviewService(
            fetcher=lambda _url: rss_feed.FetchResult(
                body=xml,
                final_url="https://pt.example/rss",
            )
        )
        result = service.run({
            "id": "poster",
            "config": {"rss_url": "https://pt.example/rss"},
        })
        self.assertEqual(result["counts"]["missing_enclosure"], 1)
        self.assertEqual(result["items"][0]["enclosure_url_masked"], "")
        self.assertNotIn("secret", repr(result))


class RssHistoryLookupTest(unittest.TestCase):
    def test_store_returns_only_matching_task_source_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = database.SQLiteStore(Path(directory) / "state.db")
            store.initialize()
            now = database.utc_now()
            with store.connection() as connection:
                connection.executemany(
                    """INSERT INTO rss_history(
                        task_id, source_key, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    [
                        ("task-a", "key-a", "queued", now, now),
                        ("task-b", "key-b", "queued", now, now),
                    ],
                )

            self.assertEqual(
                store.find_rss_source_keys("task-a", ["key-a", "key-b", "missing"]),
                {"key-a"},
            )
            self.assertEqual(store.find_rss_source_keys("", ["key-a"]), set())


if __name__ == "__main__":
    unittest.main()
