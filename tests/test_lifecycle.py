"""Host-isolated tests for the managed subscription lifecycle."""

import importlib.util
import datetime
import json
import sys
import types
import unittest
from enum import Enum
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "doubansubscribe"


def _module(name: str) -> types.ModuleType:
    value = types.ModuleType(name)
    sys.modules[name] = value
    return value


apscheduler = _module("apscheduler")
apscheduler_triggers = _module("apscheduler.triggers")
apscheduler_cron = _module("apscheduler.triggers.cron")


class CronTrigger:
    @classmethod
    def from_crontab(cls, value):
        return value


apscheduler_cron.CronTrigger = CronTrigger

app = _module("app")
app_core = _module("app.core")
app_core_event = _module("app.core.event")
app_core_config = _module("app.core.config")
app_core_metainfo = _module("app.core.metainfo")
app_db = _module("app.db")
app_db_models = _module("app.db.models")
app_db_models_subscribe = _module("app.db.models.subscribe")
app_db_subscribe_oper = _module("app.db.subscribe_oper")
app_log = _module("app.log")
app_plugins = _module("app.plugins")
app_schemas = _module("app.schemas")
app_schemas_types = _module("app.schemas.types")
app_chain = _module("app.chain")
app_chain_subscribe = _module("app.chain.subscribe")
app_chain_tmdb = _module("app.chain.tmdb")
app_utils = _module("app.utils")
app_utils_http = _module("app.utils.http")


class Event:
    def __init__(self, event_data=None):
        self.event_data = event_data


class EventManager:
    @staticmethod
    def register(*_args, **_kwargs):
        return lambda function: function


app_core_event.Event = Event
app_core_event.eventmanager = EventManager()
app_core_config.settings = types.SimpleNamespace(PROXY=None)


class MetaInfo:
    def __init__(self, title):
        self.title = title


app_core_metainfo.MetaInfo = MetaInfo


class Subscribe:
    manual_total_episode = 1


app_db_models_subscribe.Subscribe = Subscribe


class PlaceholderSubscribeOper:
    pass


app_db_subscribe_oper.SubscribeOper = PlaceholderSubscribeOper


class Logger:
    @staticmethod
    def info(*_args, **_kwargs):
        return None

    @staticmethod
    def error(*_args, **_kwargs):
        return None


app_log.logger = Logger()


class PluginBase:
    def __init__(self, *_args, **_kwargs):
        self._plugin_data = {}
        self.chain = types.SimpleNamespace()

    def get_data(self, key):
        return self._plugin_data.get(key)

    def save_data(self, key, value):
        self._plugin_data[key] = value

    def update_config(self, value):
        self._config = value


app_plugins._PluginBase = PluginBase


class SubscribeCompletionCheckEventData:
    def __init__(self, subscribe=None, mediainfo=None, meta=None):
        self.subscribe = subscribe
        self.mediainfo = mediainfo
        self.meta = meta
        self.cancel = False
        self.source = ""
        self.reason = ""


app_schemas.SubscribeCompletionCheckEventData = SubscribeCompletionCheckEventData


class ChainEventType(Enum):
    SubscribeCompletionCheck = "subscribe.completion.check"


class MediaType(Enum):
    TV = "电视剧"


app_schemas_types.ChainEventType = ChainEventType
app_schemas_types.MediaType = MediaType


class PlaceholderSubscribeChain:
    pass


app_chain_subscribe.SubscribeChain = PlaceholderSubscribeChain


class PlaceholderTmdbChain:
    pass


app_chain_tmdb.TmdbChain = PlaceholderTmdbChain


class RequestUtils:
    pass


app_utils_http.RequestUtils = RequestUtils

SPEC = importlib.util.spec_from_file_location(
    "doubansubscribe",
    PLUGIN_DIR / "__init__.py",
    submodule_search_locations=[str(PLUGIN_DIR)],
)
plugin_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plugin_module
SPEC.loader.exec_module(plugin_module)


class FakeSubscribe:
    def __init__(self, subscribe_id: int, username: str = "豆瓣订阅助手"):
        self.id = subscribe_id
        self.name = "测试剧"
        self.tmdbid = 123
        self.doubanid = "456"
        self.season = 1
        self.episode_group = None
        self.type = MediaType.TV.value
        self.total_episode = 40
        self.lack_episode = 0
        self.manual_total_episode = 1
        self.state = "R"
        self.username = username


class FakeSubscribeOper:
    records = {}

    def list(self, state=None):
        records = list(self.records.values())
        if not state:
            return records
        states = set(str(state).split(","))
        return [record for record in records if record.state in states]

    def get(self, subscribe_id):
        return self.records.get(int(subscribe_id))

    def update(self, subscribe_id, payload):
        subscribe = self.get(subscribe_id)
        if subscribe:
            for key, value in payload.items():
                setattr(subscribe, key, value)
        return subscribe

    def delete(self, subscribe_id):
        return self.records.pop(int(subscribe_id), None)


class FakeSubscribeChain:
    search_calls = []
    finish_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)

    def finish_subscribe_or_not(self, **kwargs):
        self.finish_calls.append(kwargs)
        FakeSubscribeOper().delete(kwargs["subscribe"].id)


class FakeTmdbChain:
    episodes = {}
    calls = []

    def tmdb_episodes(self, **kwargs):
        self.calls.append(kwargs)
        key = (
            kwargs.get("tmdbid"),
            kwargs.get("season"),
            kwargs.get("episode_group"),
        )
        return self.episodes.get(key, [])


class ManagedSubscriptionLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeSubscribeOper.records = {}
        FakeSubscribeChain.search_calls = []
        FakeSubscribeChain.finish_calls = []
        FakeTmdbChain.episodes = {}
        FakeTmdbChain.calls = []
        plugin_module.SubscribeOper = FakeSubscribeOper
        plugin_module.SubscribeChain = FakeSubscribeChain
        plugin_module.TmdbChain = FakeTmdbChain
        self.plugin = plugin_module.DoubanSubscribe()
        self.plugin.init_plugin({
            "enabled": True,
            "confirmation_days": 7,
            "rss_urls": "https://example.test/feed",
        })

    def _complete(self, subscribe: FakeSubscribe):
        FakeSubscribeOper.records[subscribe.id] = subscribe
        event_data = SubscribeCompletionCheckEventData(subscribe=subscribe)
        self.plugin.on_subscribe_completion_check(Event(event_data))
        return event_data

    def _make_due(self, subscribe_id: int) -> None:
        self.plugin._upsert_managed({
            "subscribe_id": subscribe_id,
            "check_after": "2000-01-01T00:00:00+08:00",
        })

    def test_completion_pauses_card_and_increased_douban_total_resumes(self) -> None:
        subscribe = FakeSubscribe(1)
        event_data = self._complete(subscribe)

        self.assertTrue(event_data.cancel)
        self.assertEqual(subscribe.state, "S")
        self.assertEqual(
            self.plugin._managed_record(1)["status"],
            "waiting_confirmation",
        )

        self._make_due(1)
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 44},
        )
        summary = self.plugin._process_due_confirmations()

        self.assertEqual(summary["resumed"], 1)
        self.assertEqual(subscribe.total_episode, 44)
        self.assertEqual(subscribe.lack_episode, 4)
        self.assertEqual(subscribe.state, "R")
        self.assertEqual(FakeSubscribeChain.search_calls[0]["sid"], 1)
        self.assertFalse(FakeSubscribeChain.search_calls[0]["manual"])

    def test_started_item_without_total_uses_provisional_100_subscription(self) -> None:
        item = plugin_module.FeedItem(
            title="测试新剧",
            source_url="https://example.test/feed",
            douban_id="654321",
        )
        candidate = plugin_module.TmdbCandidate(
            tmdb_id=321,
            title="测试新剧",
            season=1,
        )
        winner = plugin_module.ScoredCandidate(
            candidate=candidate,
            identity_score=60,
            structure_score=30,
            score=90,
        )
        decision = plugin_module.MatchDecision(
            accepted=True,
            status="matched",
            reason="matched",
            winner=winner,
        )
        mediainfo = types.SimpleNamespace(tmdb_id=321, title="测试新剧")
        captured = {}
        self.plugin._resolve_douban = lambda _item: {
            "id": "654321",
            "title": "测试新剧",
            "year": "2026",
            "countries": ["中国大陆"],
            "is_released": True,
        }
        self.plugin._match_tmdb = lambda *_args: (
            decision,
            {(321, 1): mediainfo},
        )
        self.plugin._create_subscription = lambda **kwargs: (
            captured.update(kwargs)
            or {
                "status": "subscribed",
                "subscribe_id": 88,
                "reason": "created",
                "locked": True,
                "managed": True,
            }
        )

        record = self.plugin._process_item(item)

        self.assertEqual(record["status"], "subscribed")
        self.assertTrue(record["airing_started"])
        self.assertTrue(record["total_pending"])
        self.assertEqual(captured["total_episode"], 100)
        self.assertTrue(captured["total_pending"])

    def test_pending_total_is_replaced_and_progress_is_preserved(self) -> None:
        subscribe = FakeSubscribe(8)
        subscribe.total_episode = 100
        subscribe.lack_episode = 90
        FakeSubscribeOper.records[8] = subscribe
        self.plugin._upsert_managed({
            "subscribe_id": 8,
            "title": subscribe.name,
            "douban_id": subscribe.doubanid,
            "tmdb_id": subscribe.tmdbid,
            "season": 1,
            "expected_total": 100,
            "status": "awaiting_douban_total",
            "total_pending": True,
        })
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 40},
        )

        summary = self.plugin._process_pending_totals()

        self.assertEqual(summary["pending_total_checks"], 1)
        self.assertEqual(summary["totals_resolved"], 1)
        self.assertEqual(subscribe.total_episode, 40)
        self.assertEqual(subscribe.lack_episode, 30)
        self.assertEqual(subscribe.state, "R")
        managed = self.plugin._managed_record(8)
        self.assertFalse(managed["total_pending"])
        self.assertEqual(managed["expected_total"], 40)
        self.assertEqual(managed["status"], "active")
        self.assertEqual(FakeSubscribeChain.search_calls[0]["sid"], 8)

    def test_pending_total_stays_at_100_until_douban_resolves(self) -> None:
        subscribe = FakeSubscribe(9)
        subscribe.total_episode = 100
        subscribe.lack_episode = 87
        FakeSubscribeOper.records[9] = subscribe
        self.plugin._upsert_managed({
            "subscribe_id": 9,
            "title": subscribe.name,
            "douban_id": subscribe.doubanid,
            "tmdb_id": subscribe.tmdbid,
            "season": 1,
            "expected_total": 100,
            "status": "awaiting_douban_total",
            "total_pending": True,
        })
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {},
        )

        summary = self.plugin._process_pending_totals()

        self.assertEqual(summary["pending_total_checks"], 1)
        self.assertEqual(summary["totals_resolved"], 0)
        self.assertEqual(subscribe.total_episode, 100)
        self.assertEqual(subscribe.lack_episode, 87)
        self.assertTrue(self.plugin._managed_record(9)["total_pending"])
        self.assertFalse(FakeSubscribeChain.search_calls)

    def test_pending_total_completion_keeps_card_for_periodic_recheck(self) -> None:
        subscribe = FakeSubscribe(10)
        subscribe.total_episode = 100
        subscribe.lack_episode = 0
        self.plugin._upsert_managed({
            "subscribe_id": 10,
            "title": subscribe.name,
            "douban_id": subscribe.doubanid,
            "tmdb_id": subscribe.tmdbid,
            "season": 1,
            "expected_total": 100,
            "status": "awaiting_douban_total",
            "total_pending": True,
        })

        event_data = self._complete(subscribe)

        self.assertTrue(event_data.cancel)
        self.assertEqual(subscribe.state, "S")
        managed = self.plugin._managed_record(10)
        self.assertEqual(managed["status"], "awaiting_douban_total")
        self.assertTrue(managed["total_pending"])
        self.assertTrue(managed["pending_completed"])

    def test_manually_paused_pending_total_is_not_resumed(self) -> None:
        subscribe = FakeSubscribe(11)
        subscribe.total_episode = 100
        subscribe.lack_episode = 75
        subscribe.state = "S"
        FakeSubscribeOper.records[11] = subscribe
        self.plugin._upsert_managed({
            "subscribe_id": 11,
            "title": subscribe.name,
            "douban_id": subscribe.doubanid,
            "tmdb_id": subscribe.tmdbid,
            "season": 1,
            "expected_total": 100,
            "status": "awaiting_douban_total",
            "total_pending": True,
        })
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: self.fail("手动暂停后不应再查询豆瓣"),
        )

        summary = self.plugin._process_pending_totals()

        self.assertEqual(summary["pending_total_checks"], 1)
        self.assertEqual(summary["totals_resolved"], 0)
        self.assertEqual(subscribe.total_episode, 100)
        self.assertEqual(subscribe.lack_episode, 75)
        self.assertEqual(subscribe.state, "S")
        managed = self.plugin._managed_record(11)
        self.assertEqual(managed["status"], "manual_review")
        self.assertTrue(managed["total_pending"])
        self.assertFalse(FakeSubscribeChain.search_calls)

    def test_unchanged_douban_total_normally_completes_and_removes_card(self) -> None:
        subscribe = FakeSubscribe(2)
        self._complete(subscribe)
        self._make_due(2)
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 40},
            recognize_media=lambda **_kwargs: types.SimpleNamespace(
                type=MediaType.TV,
                title_year="测试剧 (2026)",
            ),
        )

        summary = self.plugin._process_due_confirmations()

        self.assertEqual(summary["completed"], 1)
        self.assertIsNone(FakeSubscribeOper().get(2))
        self.assertEqual(self.plugin._managed_record(2)["status"], "completed")
        self.assertFalse(FakeSubscribeChain.search_calls)
        self.assertEqual(len(FakeSubscribeChain.finish_calls), 1)

    def test_decreased_douban_total_is_also_treated_as_not_increased(self) -> None:
        subscribe = FakeSubscribe(7)
        self._complete(subscribe)
        self._make_due(7)
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 36},
            recognize_media=lambda **_kwargs: types.SimpleNamespace(
                type=MediaType.TV,
                title_year="测试剧 (2026)",
            ),
        )

        summary = self.plugin._process_due_confirmations()

        self.assertEqual(summary["completed"], 1)
        self.assertIsNone(FakeSubscribeOper().get(7))
        self.assertFalse(FakeSubscribeChain.search_calls)

    def test_missing_douban_total_keeps_card_and_retries_later(self) -> None:
        subscribe = FakeSubscribe(6)
        self._complete(subscribe)
        self._make_due(6)
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {},
        )

        summary = self.plugin._process_due_confirmations()

        self.assertEqual(summary["verification_failed"], 1)
        self.assertEqual(subscribe.total_episode, 40)
        self.assertEqual(subscribe.lack_episode, 0)
        self.assertEqual(subscribe.state, "S")
        self.assertEqual(self.plugin._managed_record(6)["status"], "verification_error")
        self.assertFalse(FakeSubscribeChain.search_calls)

    def test_user_owned_subscription_is_not_intercepted(self) -> None:
        subscribe = FakeSubscribe(3, username="admin")
        event_data = self._complete(subscribe)

        self.assertFalse(event_data.cancel)
        self.assertEqual(subscribe.state, "R")
        self.assertFalse(self.plugin._managed_record(3))

    def test_manual_change_during_wait_stops_takeover(self) -> None:
        subscribe = FakeSubscribe(4)
        self._complete(subscribe)
        self._make_due(4)
        subscribe.total_episode = 50
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 40},
        )

        self.plugin._process_due_confirmations()

        self.assertEqual(subscribe.total_episode, 50)
        self.assertEqual(self.plugin._managed_record(4)["status"], "manual_review")

    def test_form_and_detail_page_are_json_serializable(self) -> None:
        subscribe = FakeSubscribe(5)
        self._complete(subscribe)

        json.dumps(self.plugin.get_form(), ensure_ascii=False)
        json.dumps(self.plugin.get_page(), ensure_ascii=False)

    def test_daily_snapshot_records_all_active_tv_subscriptions_airing_today(self) -> None:
        today = datetime.datetime(
            2026, 7, 27, 8, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        active = FakeSubscribe(20, username="admin")
        active.lack_episode = 35
        inactive = FakeSubscribe(21, username="admin")
        inactive.state = "S"
        FakeSubscribeOper.records = {20: active, 21: inactive}
        FakeTmdbChain.episodes[(123, 1, None)] = [
            types.SimpleNamespace(air_date="2026-07-27", episode_number=6),
            types.SimpleNamespace(air_date="2026-07-28", episode_number=7),
        ]

        with patch.object(
            plugin_module.DoubanSubscribe, "_now_datetime", return_value=today
        ):
            summary = self.plugin.capture_daily_supplement_snapshot()

        snapshot = self.plugin.get_data(plugin_module.SUPPLEMENT_DATA_KEY)
        self.assertTrue(summary["success"])
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["today_updates"], 1)
        self.assertEqual(snapshot["date"], "2026-07-27")
        self.assertEqual(snapshot["items"]["20"]["baseline_completed"], 5)
        self.assertEqual(snapshot["items"]["20"]["scheduled_episodes"], [6])
        self.assertEqual(snapshot["items"]["20"]["status"], "pending")

    def test_daily_supplement_searches_only_unchanged_progress(self) -> None:
        today = datetime.datetime(
            2026, 7, 27, 23, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        updated = FakeSubscribe(30, username="admin")
        updated.lack_episode = 35
        unchanged = FakeSubscribe(31, username="admin")
        unchanged.lack_episode = 35
        unchanged.tmdbid = 456
        FakeSubscribeOper.records = {30: updated, 31: unchanged}
        FakeTmdbChain.episodes[(123, 1, None)] = [
            {"air_date": "2026-07-27", "episode_number": 6},
        ]
        FakeTmdbChain.episodes[(456, 1, None)] = [
            {"air_date": "2026-07-27", "episode_number": 9},
        ]

        morning = today.replace(hour=8)
        with patch.object(
            plugin_module.DoubanSubscribe, "_now_datetime", return_value=morning
        ):
            self.plugin.capture_daily_supplement_snapshot()
        updated.lack_episode = 34

        with patch.object(
            plugin_module.DoubanSubscribe, "_now_datetime", return_value=today
        ):
            summary = self.plugin.run_daily_supplement()

        snapshot = self.plugin.get_data(plugin_module.SUPPLEMENT_DATA_KEY)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["searched"], 1)
        self.assertEqual(
            FakeSubscribeChain.search_calls,
            [{"sid": 31, "manual": True}],
        )
        self.assertEqual(snapshot["items"]["30"]["status"], "updated")
        self.assertEqual(snapshot["items"]["31"]["status"], "search_triggered")

    def test_daily_supplement_waits_between_searches_and_runs_only_once(self) -> None:
        today = datetime.datetime(
            2026, 7, 27, 23, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        first = FakeSubscribe(40, username="admin")
        first.lack_episode = 35
        second = FakeSubscribe(41, username="admin")
        second.tmdbid = 456
        second.lack_episode = 35
        FakeSubscribeOper.records = {40: first, 41: second}
        FakeTmdbChain.episodes[(123, 1, None)] = [
            {"air_date": "2026-07-27", "episode_number": 6},
        ]
        FakeTmdbChain.episodes[(456, 1, None)] = [
            {"air_date": "2026-07-27", "episode_number": 8},
        ]

        with patch.object(
            plugin_module.DoubanSubscribe,
            "_now_datetime",
            return_value=today.replace(hour=8),
        ):
            self.plugin.capture_daily_supplement_snapshot()
        with (
            patch.object(
                plugin_module.DoubanSubscribe, "_now_datetime", return_value=today
            ),
            patch.object(plugin_module.time, "sleep") as sleep,
        ):
            first_run = self.plugin.run_daily_supplement()
            second_run = self.plugin.run_daily_supplement()

        self.assertEqual(first_run["searched"], 2)
        self.assertTrue(second_run["already_finished"])
        self.assertEqual(len(FakeSubscribeChain.search_calls), 2)
        sleep.assert_called_once_with(120)

    def test_daily_supplement_never_uses_previous_day_snapshot(self) -> None:
        today = datetime.datetime(
            2026, 7, 28, 23, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        subscribe = FakeSubscribe(50, username="admin")
        subscribe.lack_episode = 35
        FakeSubscribeOper.records = {50: subscribe}
        self.plugin.save_data(plugin_module.SUPPLEMENT_DATA_KEY, {
            "date": "2026-07-27",
            "captured_at": "2026-07-27T08:00:00+08:00",
            "finished_at": "",
            "items": {
                "50": {
                    "subscribe_id": 50,
                    "tmdb_id": 123,
                    "season": 1,
                    "baseline_completed": 5,
                    "status": "pending",
                },
            },
        })

        with patch.object(
            plugin_module.DoubanSubscribe, "_now_datetime", return_value=today
        ):
            summary = self.plugin.run_daily_supplement()

        self.assertFalse(summary["success"])
        self.assertIn("不是今天", summary["message"])
        self.assertFalse(FakeSubscribeChain.search_calls)

    def test_recent_history_is_50_and_search_uses_complete_history(self) -> None:
        history = [
            {
                "key": f"item:{index}",
                "title": f"剧集 {index}",
                "status": "subscribed" if index % 2 else "existing",
                "category": "domestic",
                "reason": "测试记录",
                "time": f"2026-07-26T12:{index:02d}:00+08:00",
            }
            for index in range(75)
        ]
        history[3]["title"] = "唯一可搜索标题"
        self.plugin.save_data("history", history)

        recent = self.plugin.api_history()
        searched = self.plugin.api_search_history(keyword="唯一可搜索", limit=10)
        page = self.plugin.get_page()
        page_items = (
            page[0]["content"][1]["content"][0]["content"][0]["content"][0]
            ["props"]["items"]
        )

        self.assertEqual(recent["total"], 75)
        self.assertEqual(len(recent["items"]), 50)
        self.assertEqual(len(page_items), 50)
        self.assertEqual(searched["total"], 1)
        self.assertEqual(searched["items"][0]["key"], "item:3")

    def test_durable_processed_index_survives_history_removal(self) -> None:
        record = {
            "key": "rss:old-item",
            "title": "已经完成的旧条目",
            "status": "subscribed",
            "subscribe_id": 99,
            "time": "2026-07-01T00:00:00+08:00",
        }
        self.plugin.save_data("history", [record])

        migrated = self.plugin._processed_index()
        self.plugin.save_data("history", [])
        persisted = self.plugin._processed_index([])

        self.assertIn("rss:old-item", migrated)
        self.assertIn("rss:old-item", persisted)

    def test_sync_skips_processed_item_when_history_is_empty(self) -> None:
        item = plugin_module.FeedItem(
            title="已经处理过的剧",
            source_url="https://example.test/feed",
            douban_id="987654",
        )
        self.plugin.save_data("history", [])
        self.plugin.save_data("processed_items", {
            item.key: {"key": item.key, "status": "subscribed"},
        })
        self.plugin._fetch_feed = lambda _url: [item]
        self.plugin._process_item = lambda _item: self.fail(
            "永久索引中的条目不应再次进入订阅处理",
        )

        summary = self.plugin.sync()

        self.assertEqual(summary["items"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["subscribed"], 0)


if __name__ == "__main__":
    unittest.main()
