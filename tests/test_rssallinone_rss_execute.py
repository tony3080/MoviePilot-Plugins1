"""Formal RSS execution tests with a deterministic MoviePilot/qB gateway."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_rss_execute_tests"


def load_package_module(name):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


database = load_package_module("database")
rss_feed = load_package_module("rss_feed")
rss_execute = load_package_module("rss_execute")


TORRENT = b"d4:infod4:name8:demo.mkv6:lengthi3eee"


class FakeGateway:
    def __init__(self, *, content=TORRENT, add_results=None, existing=""):
        self.content = content
        self.add_results = list(add_results or [rss_execute.AddResult(True, "abc123")])
        self.existing = existing
        self.add_calls = []
        self.limit_calls = []
        self.sleeps = []

    def qb_server(self, downloader):
        return object()

    def site_access(self, site_id):
        return rss_execute.SiteAccess(cookie="cookie", user_agent="ua")

    def fetch_torrent(self, url, access):
        return self.content

    def find_existing(self, server, candidates):
        return self.existing

    def add_torrent(self, server, **kwargs):
        self.add_calls.append(kwargs)
        if self.add_results:
            return self.add_results.pop(0)
        return rss_execute.AddResult(False, reason="no fake result")

    def set_upload_limit(self, server, info_hash, limit_kbps):
        self.limit_calls.append((info_hash, limit_kbps))
        return True


class FakeQbServer:
    def __init__(self, state=True, added_ids=None, existing_hash=""):
        self.state = state
        self.added_ids = list(added_ids or [])
        self.existing_hash = existing_hash
        self.add_kwargs = None
        self.deleted_tags = []

    def add_torrent(self, **kwargs):
        self.add_kwargs = kwargs
        return self.state, self.added_ids

    def get_torrents(self, ids=None, tags=None):
        if ids and self.existing_hash:
            return [{"hash": self.existing_hash}], False
        return [], False

    def delete_torrents_tag(self, ids, tag):
        self.deleted_tags.append((ids, tag))
        return True


def task_config(**overrides):
    config = {
        "rss_url": "https://pt.example/rss.xml?passkey=secret",
        "qb_downloader": "qb-main",
        "qb_category": "电影",
        "save_path": "/downloads",
        "push_torrent_file": False,
        "pause_on_add": True,
        "upload_limit_kbps": 512,
    }
    config.update(overrides)
    return config


def feed_fetcher(_url):
    xml = b"""<rss><channel><title>Demo</title><item>
      <title>Demo.Movie.2026</title>
      <link>https://pt.example/details.php?id=42</link>
      <guid>opaque-demo</guid>
      <enclosure url="https://pt.example/download.php?id=42" type="application/x-bittorrent" />
    </item></channel></rss>"""
    return rss_feed.FetchResult(xml, "https://pt.example/rss.xml")


class RssExecutionServiceTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = database.SQLiteStore(Path(self.tempdir.name) / "state.db")
        self.store.initialize()

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, gateway, **config):
        background_id = config.pop("background_id", "run-1")
        service = rss_execute.RssExecutionService(
            self.store,
            gateway=gateway,
            feed_fetcher=feed_fetcher,
            sleeper=gateway.sleeps.append,
        )
        self.store.create_background_task(background_id, rss_execute.RSS_RUN_TASK_TYPE)
        return service.run(background_id, {
            "id": "task-1",
            "name": "Demo",
            "enabled": True,
            "config": task_config(**config),
        })

    def test_url_mode_enqueues_with_task_category_pause_and_limit(self):
        gateway = FakeGateway()
        result = self._run(gateway)

        self.assertEqual(result["queued"], 1)
        self.assertEqual(gateway.add_calls[0]["mode"], "url")
        self.assertEqual(gateway.add_calls[0]["content"], "https://pt.example/download.php?id=42")
        self.assertEqual(gateway.add_calls[0]["category"], "电影")
        self.assertTrue(gateway.add_calls[0]["paused"])
        self.assertEqual(gateway.limit_calls, [("abc123", 512)])
        row = self.store.list_rss_history()["items"][0]
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["content_key"], "qb-main:abc123")

    def test_file_preference_falls_back_to_url_after_four_attempts(self):
        gateway = FakeGateway(add_results=[
            rss_execute.AddResult(False, reason="temporary") for _ in range(4)
        ] + [rss_execute.AddResult(True, "abc123")])
        result = self._run(gateway, push_torrent_file=True, upload_limit_kbps=0)

        self.assertEqual(result["queued"], 1)
        self.assertEqual([call["mode"] for call in gateway.add_calls], ["file"] * 4 + ["url"])
        self.assertEqual(gateway.sleeps, [3, 10, 30])
        self.assertEqual(gateway.limit_calls, [("abc123", 0)])

    def test_second_run_uses_source_history_without_writing_qb(self):
        gateway = FakeGateway()
        self._run(gateway, background_id="run-1")
        second = self._run(gateway, background_id="run-2")

        self.assertEqual(second["duplicate_source"], 1)
        self.assertEqual(len(gateway.add_calls), 1)

    def test_existing_qb_hash_is_not_enqueued(self):
        gateway = FakeGateway(existing="existing123")
        result = self._run(gateway)

        self.assertEqual(result["existing"], 1)
        self.assertEqual(gateway.add_calls, [])


class MoviePilotRssGatewayTest(unittest.TestCase):
    def test_internal_lookup_tag_is_removed_and_category_is_preserved(self):
        server = FakeQbServer(state=True, added_ids=["ABC123"])
        result = rss_execute.MoviePilotRssGateway().add_torrent(
            server,
            content="https://pt.example/download.php?id=42",
            mode="url",
            save_path="/downloads",
            category="电影",
            paused=True,
            cookie="cookie",
            hash_candidates=[],
        )

        self.assertTrue(result.success)
        self.assertEqual(server.add_kwargs["category"], "电影")
        temporary_tag = server.add_kwargs["tag"][0]
        self.assertTrue(temporary_tag.startswith("rssallinone-"))
        self.assertEqual(server.deleted_tags, [(["abc123"], temporary_tag)])

    def test_duplicate_path_also_removes_internal_lookup_tag(self):
        server = FakeQbServer(state=False, existing_hash="existing123")
        result = rss_execute.MoviePilotRssGateway().add_torrent(
            server,
            content=TORRENT,
            mode="file",
            save_path="/downloads",
            category="电影",
            paused=True,
            cookie="cookie",
            hash_candidates=["candidate"],
        )

        self.assertTrue(result.existing)
        temporary_tag = server.add_kwargs["tag"][0]
        self.assertEqual(server.deleted_tags, [(["existing123"], temporary_tag)])


if __name__ == "__main__":
    unittest.main()
