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
rss_site_labels = load_package_module("rss_site_labels")
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


class FakeRenamer:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {
            "status": "renamed",
            "chinese_title": "演示电影",
            "final_files": [{"index": 0, "name": "[演示电影].Demo.Movie.mkv"}],
        }

    def apply(self, server, info_hash, **kwargs):
        self.calls.append((server, info_hash, kwargs))
        return dict(self.result)


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

    def _run(
        self,
        gateway,
        renamer=None,
        label_service=None,
        on_source_ready=None,
        media_category_resolver=None,
        **config,
    ):
        background_id = config.pop("background_id", "run-1")
        service = rss_execute.RssExecutionService(
            self.store,
            gateway=gateway,
            renamer=renamer,
            label_service=label_service,
            on_source_ready=on_source_ready,
            media_category_resolver=media_category_resolver,
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

    def test_source_rename_runs_after_enqueue_and_is_saved_in_history(self):
        gateway = FakeGateway()
        renamer = FakeRenamer()
        result = self._run(
            gateway,
            renamer=renamer,
            rename_enabled=True,
            rename_rules="Demo => Release",
            add_chinese_title=True,
        )

        self.assertEqual(result["queued"], 1)
        self.assertEqual(renamer.calls[0][1], "abc123")
        self.assertEqual(renamer.calls[0][2]["rename_rules"], "Demo => Release")
        row = self.store.list_rss_history()["items"][0]
        self.assertEqual(row["payload"]["source_rename"]["status"], "renamed")
        self.assertEqual(
            row["payload"]["source_rename"]["final_files"][0]["name"],
            "[演示电影].Demo.Movie.mkv",
        )

    def test_source_rename_failure_keeps_dedup_history_as_warning(self):
        gateway = FakeGateway()
        renamer = FakeRenamer({"status": "failed", "error": "rename rejected"})
        result = self._run(gateway, renamer=renamer, rename_enabled=True)

        self.assertEqual(result["queued_warning"], 1)
        row = self.store.list_rss_history()["items"][0]
        self.assertEqual(row["status"], "queued_warning")
        self.assertIn("rename rejected", row["reason"])

    def test_qb_card_is_created_only_after_all_source_name_stages(self):
        events = []

        class OrderedRenamer(FakeRenamer):
            def apply(self, server, info_hash, **kwargs):
                events.append(
                    "marker_rename"
                    if kwargs.get("add_cn") or kwargs.get("add_fx")
                    else "base_rename"
                )
                self.calls.append((server, info_hash, kwargs))
                return {
                    "status": "renamed",
                    "final_files": [{
                        "index": 0,
                        "name": (
                            "[演示电影].Demo.Movie-国配-特效.mkv"
                            if kwargs.get("add_cn") or kwargs.get("add_fx")
                            else "[演示电影].Demo.Movie.mkv"
                        ),
                    }],
                }

        class Labels:
            @staticmethod
            def detect(**_kwargs):
                events.append("site_labels")
                return {
                    "status": "matched",
                    "mandarin": True,
                    "effects": True,
                }

        def source_ready(downloader, info_hash):
            history = self.store.latest_rss_history_for_torrent(
                downloader, info_hash
            )
            self.assertEqual(history["payload"]["site_labels"]["status"], "matched")
            self.assertEqual(
                history["payload"]["source_rename"]["final_files"][0]["name"],
                "[演示电影].Demo.Movie-国配-特效.mkv",
            )
            events.append("mp_recognition")

        result = self._run(
            FakeGateway(),
            renamer=OrderedRenamer(),
            label_service=Labels(),
            on_source_ready=source_ready,
            media_category_resolver=lambda _title: (
                events.append("media_category") or "外语电影"
            ),
            rename_enabled=True,
            add_chinese_title=True,
            recognize_cn=True,
            recognize_fx=True,
        )

        self.assertEqual(events, [
            "base_rename", "media_category", "site_labels", "marker_rename",
            "mp_recognition",
        ])
        self.assertEqual(result["qb_recognized"], 1)
        self.assertEqual(result["qb_recognition_deferred"], 0)

    def test_mandarin_category_allowlist_is_exact(self):
        for category in ("", "外语电影", "动画电影", "未识别", "未分类"):
            with self.subTest(category=category):
                self.assertTrue(rss_execute._allows_mandarin_category(category))
        for category in ("华语电影", "国产剧", "欧美剧", "纪录片", "动漫"):
            with self.subTest(category=category):
                self.assertFalse(rss_execute._allows_mandarin_category(category))

    def test_disabled_label_options_do_not_run_category_resolution(self):
        category_calls = []
        self._run(
            FakeGateway(),
            media_category_resolver=lambda title: category_calls.append(title),
        )

        self.assertEqual(category_calls, [])
        history = self.store.list_rss_history()["items"][0]
        site_labels = history["payload"]["site_labels"]
        self.assertFalse(site_labels["requested"])
        self.assertEqual(site_labels["status"], "skipped")

    def test_disallowed_category_skips_mandarin_site_request(self):
        class Labels:
            def __init__(self):
                self.calls = []

            def detect(self, **kwargs):
                self.calls.append(kwargs)
                return {"status": "matched", "mandarin": True, "effects": False}

        labels = Labels()
        renamer = FakeRenamer()
        result = self._run(
            FakeGateway(),
            renamer=renamer,
            label_service=labels,
            media_category_resolver=lambda _title: "国产剧",
            recognize_cn=True,
        )

        self.assertEqual(result["queued"], 1)
        self.assertEqual(labels.calls, [])
        self.assertEqual(len(renamer.calls), 1)
        history = self.store.list_rss_history()["items"][0]
        site_labels = history["payload"]["site_labels"]
        self.assertEqual(site_labels["status"], "skipped")
        self.assertEqual(site_labels["media_category"], "国产剧")
        self.assertFalse(site_labels["mandarin_allowed"])

    def test_disallowed_mandarin_category_still_checks_effects(self):
        class Labels:
            def __init__(self):
                self.calls = []

            def detect(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "status": "matched",
                    "mandarin": bool(kwargs["recognize_cn"]),
                    "effects": bool(kwargs["recognize_fx"]),
                }

        labels = Labels()
        renamer = FakeRenamer()
        self._run(
            FakeGateway(),
            renamer=renamer,
            label_service=labels,
            media_category_resolver=lambda _title: "纪录片",
            recognize_cn=True,
            recognize_fx=True,
        )

        self.assertEqual(len(labels.calls), 1)
        self.assertFalse(labels.calls[0]["recognize_cn"])
        self.assertTrue(labels.calls[0]["recognize_fx"])
        self.assertEqual(len(renamer.calls), 2)
        self.assertFalse(renamer.calls[1][2]["add_cn"])
        self.assertTrue(renamer.calls[1][2]["add_fx"])

    def test_failed_source_rename_defers_initial_qb_card(self):
        callbacks = []
        result = self._run(
            FakeGateway(),
            renamer=FakeRenamer({"status": "failed", "error": "rename rejected"}),
            on_source_ready=lambda *_args: callbacks.append(True),
            rename_enabled=True,
        )

        self.assertEqual(callbacks, [])
        self.assertEqual(result["qb_recognition_deferred"], 1)


class SiteLabelParsingTest(unittest.TestCase):
    def test_ubits_without_detail_url_does_not_search_by_default(self):
        class Gateway:
            calls = []

            @classmethod
            def fetch_site_html(cls, url, access):
                cls.calls.append(url)
                return "<html></html>"

        access = types.SimpleNamespace(
            site_key="UBits",
            site_url="https://ubits.club",
            referer="https://ubits.club",
        )
        labels = rss_site_labels.SiteLabelService(
            Gateway(), sleeper=lambda _seconds: None
        ).detect(
            access=access,
            title="Demo 2026 1080p",
            detail_url="",
            torrent_id="",
            cn_keywords="国语,国配",
            recognize_cn=True,
            recognize_fx=False,
        )
        self.assertEqual(Gateway.calls, [])
        self.assertEqual(labels["status"], "failed")
        self.assertIn("缺少详情页链接", labels["reason"])

    def test_ubits_without_detail_url_falls_back_to_search(self):
        search_page = """
          <tr><td><a href="details.php?id=42">Demo</a>
            <span class="tag">国语</span><span class="tag">特效字幕</span>
          </td></tr>
        """

        class Gateway:
            @staticmethod
            def fetch_site_html(url, access):
                return search_page

        access = types.SimpleNamespace(
            site_key="UBits",
            site_url="https://ubits.club",
            referer="https://ubits.club",
        )
        labels = rss_site_labels.SiteLabelService(
            Gateway(), sleeper=lambda _seconds: None
        ).detect(
            access=access,
            title="Demo 2026 1080p",
            detail_url="",
            torrent_id="",
            cn_keywords="国语,国配",
            recognize_cn=True,
            recognize_fx=True,
            allow_search_without_detail=True,
        )
        self.assertEqual(labels["status"], "matched")
        self.assertTrue(labels["mandarin"])
        self.assertTrue(labels["effects"])
        self.assertIn("details.php?id=42", labels["request_url_masked"])

    def test_ubits_only_reads_the_tags_row(self):
        page = """
          <table><tr><td>标签</td><td>
            <a href="tags.php?tag_id5=1"><span class="tag">国语</span></a>
            <span class="tag">特效字幕</span>
          </td></tr></table>
          <div class="recommend"><span class="tag">无关国语</span></div>
        """
        self.assertEqual(
            rss_site_labels.parse_ubits_labels(page, ["国语", "国配"]),
            (True, True),
        )

    def test_site_label_text_ignores_entities_and_whitespace(self):
        block = '<span class="optiontag">国&nbsp; 配</span>'
        self.assertEqual(
            rss_site_labels.parse_hdsky_labels(block, ["国语", "国配"]),
            (True, False),
        )

    def test_ubits_rebuilds_canonical_detail_url_from_torrent_id(self):
        access = types.SimpleNamespace(
            site_url="https://ubits.club/",
            referer="https://ubits.club/",
        )
        self.assertEqual(
            rss_site_labels._ubits_detail_url(
                access,
                "https://rss.example/redirect?passkey=secret",
                "42",
            ),
            "https://ubits.club/details.php?id=42",
        )

    def test_chd_multiple_results_require_exact_rss_torrent_id(self):
        page = """
          <tr><td><a href="details.php?id=41">A</a><div class="tag-gy">国语</div></td></tr>
          <tr><td><a href="details.php?id=42">B</a><div class="tag-txsub">特效</div></td></tr>
        """
        block, selected = rss_site_labels.select_exact_result(page, "42")
        self.assertEqual(selected, "42")
        self.assertEqual(
            rss_site_labels.parse_chd_labels(block, ["国语", "国配"]),
            (False, True),
        )
        with self.assertRaises(rss_site_labels.SiteLabelError):
            rss_site_labels.select_exact_result(page, "")

    def test_hdsky_optiontag_text_controls_both_labels(self):
        block = """
          <span class="optiontag selected">国配</span>
          <span class="optiontag">特效字幕</span>
        """
        self.assertEqual(
            rss_site_labels.parse_hdsky_labels(block, ["国语", "国配"]),
            (True, True),
        )


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

    def test_rename_adapter_uses_qbittorrent_api_file_and_folder_calls(self):
        class Qbc:
            def __init__(self):
                self.calls = []

            def torrents_rename_file(self, **kwargs):
                self.calls.append(("file", kwargs))

            def torrents_rename_folder(self, **kwargs):
                self.calls.append(("folder", kwargs))

        server = types.SimpleNamespace(qbc=Qbc())
        gateway = rss_execute.MoviePilotRssGateway()
        gateway.rename_torrent_file(server, "abc123", "Old.mkv", "New.mkv")
        gateway.rename_torrent_folder(server, "abc123", "Old", "New")

        self.assertEqual(server.qbc.calls[0][1], {
            "torrent_hash": "abc123",
            "old_path": "Old.mkv",
            "new_path": "New.mkv",
        })
        self.assertEqual(server.qbc.calls[1][1], {
            "torrent_hash": "abc123",
            "old_path": "Old",
            "new_path": "New",
        })


if __name__ == "__main__":
    unittest.main()
