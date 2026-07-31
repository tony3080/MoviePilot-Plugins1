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

    @staticmethod
    def warning(*_args, **_kwargs):
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


class LimitException(Exception):
    pass


app_schemas.LimitException = LimitException


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
    history = set()

    def list(self, state=None):
        records = list(self.records.values())
        if not state:
            return records
        states = set(str(state).split(","))
        return [record for record in records if record.state in states]

    def get(self, subscribe_id):
        return self.records.get(int(subscribe_id))

    def get_by(self, type=None, season=None, tmdbid=None):
        return next(
            (
                record for record in self.records.values()
                if record.type == type
                and record.season == season
                and record.tmdbid == tmdbid
            ),
            None,
        )

    def exist_history(self, tmdbid=None, season=None):
        return (tmdbid, season) in self.history

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
    add_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)

    def finish_subscribe_or_not(self, **kwargs):
        self.finish_calls.append(kwargs)
        FakeSubscribeOper().delete(kwargs["subscribe"].id)

    def add(self, **kwargs):
        self.add_calls.append(kwargs)
        return None, "unexpected add"


class FakeTmdbChain:
    episodes = {}
    seasons = {}
    calls = []

    def tmdb_episodes(self, **kwargs):
        self.calls.append(kwargs)
        key = (
            kwargs.get("tmdbid"),
            kwargs.get("season"),
            kwargs.get("episode_group"),
        )
        return self.episodes.get(key, [])

    def tmdb_seasons(self, tmdbid):
        self.calls.append({"tmdbid": tmdbid, "method": "tmdb_seasons"})
        return self.seasons.get(tmdbid, [])


class ManagedSubscriptionLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeSubscribeOper.records = {}
        FakeSubscribeOper.history = set()
        FakeSubscribeChain.search_calls = []
        FakeSubscribeChain.finish_calls = []
        FakeSubscribeChain.add_calls = []
        FakeTmdbChain.episodes = {}
        FakeTmdbChain.seasons = {}
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
        self.plugin._tmdb_raw_tv_search = lambda _title, _year: []

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
            [],
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

    def test_disabled_category_is_cached_before_imdb_and_tmdb(self) -> None:
        item = plugin_module.FeedItem(
            title="碧蓝之海 第三季",
            guid="maoyan:tv:37425956",
            source_url="https://piaofang.maoyan.com/test",
        )
        self.plugin._media_categories = ["domestic"]
        self.plugin._resolve_douban = lambda _item: {
            "id": "37425956",
            "title": "碧蓝之海 第三季",
            "year": "2026",
            "episodes_count": 12,
            "countries": ["日本"],
        }
        self.plugin._resolve_douban_imdb_id = lambda _info: self.fail(
            "地区跳过前不应读取 IMDb 信息页"
        )
        self.plugin._match_tmdb = lambda *_args: self.fail(
            "地区跳过后不应查询 TMDB"
        )

        record = self.plugin._process_item(item)

        self.assertEqual(record["status"], "category_skipped")
        self.assertEqual(record["category"], "japan_korea")
        cached = self.plugin.get_data(plugin_module.CATEGORY_SKIP_DATA_KEY)
        self.assertEqual(cached[item.key]["douban_id"], "37425956")
        self.assertEqual(cached["douban:37425956"]["category"], "japan_korea")

    def test_category_cache_skips_next_source_run_without_processing(self) -> None:
        item = plugin_module.FeedItem(
            title="X战警97 第二季",
            guid="maoyan:tv:36010991",
            source_url="https://piaofang.maoyan.com/test",
        )
        self.plugin._media_categories = ["domestic"]
        previous_history = [{
            **item.to_dict(),
            "status": "category_skipped",
            "reason": "欧美剧未在订阅类型中启用",
            "time": "2026-07-29T09:01:49+08:00",
            "douban_id": "36010991",
            "douban_title": item.title,
            "douban_total": 9,
            "category": "western",
            "countries": ["美国"],
        }]
        self.plugin.save_data("history", previous_history)
        self.assertIsNone(self.plugin.get_data(plugin_module.CATEGORY_SKIP_DATA_KEY))
        self.plugin._process_item = lambda _item: self.fail(
            "历史迁移后的地区缓存不应进入豆瓣处理流程"
        )
        summary = {
            "items": 0,
            "subscribed": 0,
            "existing": 0,
            "skipped": 0,
            "failed": 0,
        }

        stopped = self.plugin._process_source_items(
            items=[item],
            history=previous_history,
            processed_items={},
            completed_keys=set(),
            summary=summary,
        )

        self.assertFalse(stopped)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(previous_history[0]["status"], "category_skipped")
        self.assertIn("地区缓存命中，未请求豆瓣", previous_history[0]["reason"])
        migrated = self.plugin.get_data(plugin_module.CATEGORY_SKIP_DATA_KEY)
        self.assertEqual(migrated[item.key]["douban_id"], "36010991")
        self.assertEqual(migrated["douban:36010991"]["category"], "western")

    def test_enabling_cached_category_reenters_processing(self) -> None:
        item = plugin_module.FeedItem(
            title="穹庐下的魔女",
            douban_id="37315819",
        )
        self.plugin.save_data(plugin_module.CATEGORY_SKIP_DATA_KEY, {
            item.key: {
                "douban_id": "37315819",
                "category": "japan_korea",
            },
        })
        self.plugin._media_categories = ["domestic", "japan_korea"]
        calls = []

        def process_item(value):
            calls.append(value.key)
            return {
                **value.to_dict(),
                "status": "no_candidate",
                "reason": "test",
            }

        self.plugin._process_item = process_item
        summary = {
            "items": 0,
            "subscribed": 0,
            "existing": 0,
            "skipped": 0,
            "failed": 0,
        }

        self.plugin._process_source_items(
            items=[item],
            history=[],
            processed_items={},
            completed_keys=set(),
            summary=summary,
        )

        self.assertEqual(calls, [item.key])
        self.assertEqual(summary["failed"], 1)

    def test_douban_alias_reuses_category_skip_across_sources(self) -> None:
        maoyan_item = plugin_module.FeedItem(
            title="斯图尔特未能拯救宇宙",
            guid="maoyan:web:36358245",
        )
        self.plugin._media_categories = ["domestic"]
        self.plugin._remember_category_skip(maoyan_item, {
            "title": maoyan_item.title,
            "douban_id": "36358245",
            "douban_title": maoyan_item.title,
            "douban_total": 10,
            "category": "western",
            "countries": ["美国"],
            "status": "category_skipped",
            "time": "2026-07-29T09:01:43+08:00",
        })
        rss_item = plugin_module.FeedItem(
            title="Stuart Fails to Save the Universe",
            douban_id="36358245",
            source_url="https://example.test/feed",
        )

        cached = self.plugin._cached_category_skip(rss_item)

        self.assertIsNotNone(cached)
        self.assertEqual(cached["douban_id"], "36358245")
        self.assertEqual(cached["category"], "western")

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

        self.assertEqual(recent["total"], 75)
        self.assertEqual(len(recent["items"]), 50)
        self.assertEqual(self.plugin.get_page(), [])
        self.assertEqual(searched["total"], 1)
        self.assertEqual(searched["items"][0]["key"], "item:3")

    def test_history_group_filter_and_single_record_retry(self) -> None:
        failed = {
            "key": "douban:100",
            "title": "失败剧集",
            "douban_id": "100",
            "status": "tmdb_search_empty",
            "reason": "empty",
            "time": "2026-07-27T12:00:00+08:00",
        }
        self.plugin.save_data("history", [
            failed,
            {
                "key": "douban:101",
                "title": "成功剧集",
                "status": "subscribed",
            },
        ])
        filtered = self.plugin.api_search_history(group="failure")
        self.assertEqual(filtered["total"], 1)
        self.assertTrue(filtered["items"][0]["retryable"])
        self.plugin._process_item = lambda item: {
            **item.to_dict(),
            "status": "history_existing",
            "reason": "history",
            "time": "2026-07-27T13:00:00+08:00",
        }

        retried = self.plugin.api_retry_history({"key": "douban:100"})

        self.assertTrue(retried["success"])
        stored = self.plugin.get_data("history")
        self.assertEqual(len(stored), 2)
        self.assertEqual(
            next(item for item in stored if item["key"] == "douban:100")["status"],
            "history_existing",
        )
        self.assertIn("douban:100", self.plugin.get_data("processed_items"))

    def test_subscription_history_same_tmdb_and_season_is_skipped(self) -> None:
        FakeSubscribeOper.history = {(123, 2)}
        mediainfo = types.SimpleNamespace(
            tmdb_id=123,
            title="测试剧",
            year="2026",
        )

        result = self.plugin._create_subscription(
            mediainfo=mediainfo,
            douban_id="456",
            season=2,
            total_episode=12,
            category="domestic",
            source_key="douban:456",
        )

        self.assertEqual(result["status"], "history_existing")
        self.assertEqual(FakeSubscribeChain.add_calls, [])

    def test_arc_title_uses_tmdb_season_name_to_select_real_season(self) -> None:
        media = types.SimpleNamespace(
            tmdb_id=85937,
            title="鬼灭之刃",
            original_title="鬼滅の刃",
            names=[],
            year="2019",
            seasons={},
            season_years={},
            actors=[],
            directors=[],
        )
        self.plugin.chain = types.SimpleNamespace(
            search_medias=lambda **_kwargs: [types.SimpleNamespace(tmdb_id=85937)],
            recognize_media=lambda **_kwargs: media,
        )
        FakeTmdbChain.seasons[85937] = [
            types.SimpleNamespace(
                season_number=1,
                name="竈門炭治郎 立志篇",
                episode_count=26,
                air_date="2019-04-06",
            ),
            types.SimpleNamespace(
                season_number=2,
                name="无限列车篇",
                episode_count=7,
                air_date="2021-10-10",
            ),
        ]

        decision, _media, attempts = self.plugin._match_tmdb({
            "title": "鬼灭之刃 无限列车篇",
            "year": "2021",
            "episodes_count": 7,
        }, 7)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.season, 2)
        self.assertTrue(any(item["mode"] == "arc_title" for item in attempts))

    def test_numeric_suffix_finds_parent_through_explicit_season_query(self) -> None:
        parent = types.SimpleNamespace(
            tmdb_id=374627,
            title="二龙湖·村暖花开",
            original_title="",
            names=["二龙湖·村暖花开3"],
            year="2024",
            seasons={1: [object()], 2: [object()], 3: [object()] * 24},
            season_years={3: "2026"},
            actors=["张浩", "朱丽岚"],
            directors=["张浩"],
        )
        queries = []

        def search_medias(meta, **_kwargs):
            queries.append(meta.name)
            if meta.name == "二龙湖·村暖花开 第三季":
                return [types.SimpleNamespace(tmdb_id=374627)]
            return []

        self.plugin.chain = types.SimpleNamespace(
            search_medias=search_medias,
            recognize_media=lambda **_kwargs: parent,
        )

        decision, media_by_key, _attempts = self.plugin._match_tmdb({
            "title": "二龙湖·村暖花开3",
            "year": "2026",
            "episodes_count": 24,
            "actors": [{"name": "张浩"}, {"name": "朱丽岚"}],
            "directors": [{"name": "张浩"}],
        }, 24)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.tmdb_id, 374627)
        self.assertEqual(decision.winner.candidate.season, 3)
        self.assertIn((374627, 3), media_by_key)
        self.assertIn("二龙湖·村暖花开", queries)
        self.assertIn("二龙湖·村暖花开 第3季", queries)
        self.assertIn("二龙湖·村暖花开 第三季", queries)

    def test_raw_tmdb_fallback_recovers_moviepilot_filtered_parent(self) -> None:
        parent = types.SimpleNamespace(
            tmdb_id=270845,
            title="二龙湖·“村”暖花开",
            original_title="",
            names=[],
            year="2024",
            seasons={1: [object()] * 24, 2: [object()] * 28, 3: [object()] * 24},
            season_years={1: "2024", 2: "2025", 3: "2026"},
            actors=["张浩", "朱丽岚"],
            directors=["张浩"],
        )
        raw_calls = []

        def raw_search(title, year):
            raw_calls.append((title, year))
            if title == "二龙湖·村暖花开":
                return [{"tmdb_id": 270845}]
            return []

        self.plugin._tmdb_raw_tv_search = raw_search
        self.plugin.chain = types.SimpleNamespace(
            search_medias=lambda **_kwargs: [],
            recognize_media=lambda **_kwargs: parent,
        )

        decision, media_by_key, attempts = self.plugin._match_tmdb({
            "title": "二龙湖·村暖花开3",
            "year": "2026",
            "episodes_count": 24,
            "actors": [{"name": "张浩"}, {"name": "朱丽岚"}],
            "directors": [{"name": "张浩"}],
        }, 24)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.tmdb_id, 270845)
        self.assertEqual(decision.winner.candidate.season, 3)
        self.assertIn((270845, 3), media_by_key)
        self.assertEqual(raw_calls, [("二龙湖·村暖花开", None)])
        fallback_attempt = next(
            item for item in attempts if item["raw_fallback"]
        )
        self.assertEqual(fallback_attempt["query"], "二龙湖·村暖花开")
        self.assertEqual(fallback_attempt["result_count"], 1)
        self.assertEqual(fallback_attempt["error"], "")

    def test_raw_tmdb_search_uses_moviepilot_client_and_closes_it(self) -> None:
        calls = []

        class Search:
            def __init__(self, language=None):
                calls.append(("init", language))

            def tv_shows(self, term, release_year=None):
                calls.append(("search", term, release_year))
                return [{"id": 270845}, {"name": "missing id"}]

            def close(self):
                calls.append(("close",))

        tmdb_module = types.ModuleType("app.modules.themoviedb.tmdbv3api")
        tmdb_module.Search = Search
        with patch.dict(sys.modules, {
            "app.modules.themoviedb.tmdbv3api": tmdb_module,
        }):
            results = plugin_module.DoubanSubscribe._tmdb_raw_tv_search(
                "二龙湖·村暖花开",
                None,
            )

        self.assertEqual(results, [{"tmdb_id": 270845}])
        self.assertEqual(calls, [
            ("init", None),
            ("search", "二龙湖·村暖花开", None),
            ("close",),
        ])

    def test_numeric_suffix_rejects_standalone_sequel_s01(self) -> None:
        standalone = types.SimpleNamespace(
            tmdb_id=999003,
            title="二龙湖·村暖花开 第三季",
            original_title="",
            names=["二龙湖·村暖花开3"],
            year="2026",
            seasons={1: [object()] * 24},
            season_years={1: "2026"},
            actors=["张浩", "朱丽岚"],
            directors=["张浩"],
        )

        def search_medias(meta, **_kwargs):
            if meta.name == "二龙湖·村暖花开 第三季":
                return [types.SimpleNamespace(tmdb_id=999003)]
            return []

        self.plugin.chain = types.SimpleNamespace(
            search_medias=search_medias,
            recognize_media=lambda **_kwargs: standalone,
        )

        decision, media_by_key, attempts = self.plugin._match_tmdb({
            "title": "二龙湖·村暖花开3",
            "year": "2026",
            "episodes_count": 24,
            "actors": [{"name": "张浩"}, {"name": "朱丽岚"}],
            "directors": [{"name": "张浩"}],
        }, 24)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "no_candidate")
        self.assertIn("父剧不存在目标季度 S03", decision.reason)
        self.assertIn("独立续季条目的 S01", decision.reason)
        self.assertEqual(media_by_key, {})
        self.assertTrue(any(
            item["parent_season_rejections"] for item in attempts
        ))

    def test_standalone_imdb_match_falls_back_to_parent_season(self) -> None:
        standalone = types.SimpleNamespace(
            tmdb_id=999003,
            title="二龙湖·村暖花开 第三季",
            original_title="",
            names=["二龙湖·村暖花开3"],
            year="2026",
            seasons={1: [object()] * 24},
            season_years={1: "2026"},
            actors=["张浩", "朱丽岚"],
            directors=["张浩"],
        )
        parent = types.SimpleNamespace(
            tmdb_id=374627,
            title="二龙湖·村暖花开",
            original_title="",
            names=["二龙湖·村暖花开3"],
            year="2024",
            seasons={1: [object()], 2: [object()], 3: [object()] * 24},
            season_years={3: "2026"},
            actors=["张浩", "朱丽岚"],
            directors=["张浩"],
        )
        self.plugin._tmdb_find_by_imdb_id = lambda _imdb_id: {
            "tv_results": [{"id": 999003}],
        }

        def search_medias(meta, **_kwargs):
            if meta.name == "二龙湖·村暖花开 第三季":
                return [types.SimpleNamespace(tmdb_id=374627)]
            return []

        self.plugin.chain = types.SimpleNamespace(
            search_medias=search_medias,
            recognize_media=lambda tmdbid, **_kwargs: (
                standalone if tmdbid == 999003 else parent
            ),
        )

        decision, media_by_key, attempts = self.plugin._match_tmdb({
            "title": "二龙湖·村暖花开3",
            "year": "2026",
            "episodes_count": 24,
            "actors": [{"name": "张浩"}, {"name": "朱丽岚"}],
            "directors": [{"name": "张浩"}],
            "imdb_id": "tt9999003",
        }, 24)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.tmdb_id, 374627)
        self.assertEqual(decision.winner.candidate.season, 3)
        self.assertNotIn((999003, 1), media_by_key)
        self.assertEqual(attempts[0]["mode"], "imdb_exact")
        self.assertEqual(attempts[0]["rejected_parent_seasons"], [3])

    def test_first_season_can_still_match_a_new_tmdb_show(self) -> None:
        media = types.SimpleNamespace(
            tmdb_id=100001,
            title="测试新剧 第一季",
            original_title="",
            names=[],
            year="2026",
            seasons={1: [object()] * 12},
            season_years={1: "2026"},
            actors=["演员甲", "演员乙"],
            directors=[],
        )
        self.plugin.chain = types.SimpleNamespace(
            search_medias=lambda **_kwargs: [types.SimpleNamespace(tmdb_id=100001)],
            recognize_media=lambda **_kwargs: media,
        )

        decision, media_by_key, _attempts = self.plugin._match_tmdb({
            "title": "测试新剧 第一季",
            "year": "2026",
            "episodes_count": 12,
            "actors": [{"name": "演员甲"}, {"name": "演员乙"}],
        }, 12)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.season, 1)
        self.assertIn((100001, 1), media_by_key)

    def test_tmdb_search_error_retries_and_records_diagnostics(self) -> None:
        calls = []

        def fail_search(**_kwargs):
            calls.append(True)
            raise RuntimeError("timeout")

        self.plugin.chain = types.SimpleNamespace(search_medias=fail_search)
        with patch.object(plugin_module.time, "sleep") as sleep:
            decision, _media, attempts = self.plugin._match_tmdb({
                "title": "测试剧",
                "year": "2026",
            }, 12)

        self.assertEqual(decision.status, "tmdb_search_error")
        self.assertEqual(len(calls), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 5])
        self.assertEqual(attempts[0]["request_count"], 3)
        self.assertEqual(attempts[0]["error"], "timeout")

    def test_douban_full_info_page_supplies_imdb_id(self) -> None:
        self.plugin._run_douban_request = lambda _callable: types.SimpleNamespace(
            status_code=200,
            text="<tr><td>IMDb</td><td>tt35288698</td></tr>",
        )

        imdb_id = self.plugin._resolve_douban_imdb_id({
            "id": "37042229",
            "info_url": "https://www.douban.com/doubanapp/h5/movie/37042229/desc",
        })

        self.assertEqual(imdb_id, "tt35288698")
        self.assertEqual(
            self.plugin._douban_imdb_cache["37042229"],
            "tt35288698",
        )

    def test_imdb_exact_match_precedes_title_search(self) -> None:
        media = types.SimpleNamespace(
            tmdb_id=9988,
            title="改名后的电视剧",
            original_title="",
            names=[],
            year="2026",
            seasons={1: [object()]},
            season_years={1: "2026"},
            actors=[],
            directors=[],
        )
        self.plugin._tmdb_find_by_imdb_id = lambda _imdb_id: {
            "tv_results": [{"id": 9988}],
        }
        self.plugin.chain = types.SimpleNamespace(
            recognize_media=lambda **_kwargs: media,
            search_medias=lambda **_kwargs: self.fail("IMDb 命中后不应执行标题搜索"),
        )

        decision, media_by_key, attempts = self.plugin._match_tmdb({
            "title": "醉梦",
            "year": "2026",
            "imdb_id": "tt35288698",
        }, 16)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.tmdb_id, 9988)
        self.assertIn("IMDb ID 精确关联", decision.winner.evidence)
        self.assertIn((9988, 1), media_by_key)
        self.assertEqual([item["mode"] for item in attempts], ["imdb_exact"])

    def test_imdb_empty_result_falls_back_and_rejects_wrong_title(self) -> None:
        wrong_media = types.SimpleNamespace(
            tmdb_id=312575,
            title="醉梦春夜",
            original_title="醉梦春夜",
            names=["坠梦春夜"],
            year="2026",
            seasons={1: [object(), object()]},
            season_years={1: "2026"},
            actors=["刘兰博", "时童", "李思颖"],
            directors=[],
        )
        self.plugin._tmdb_find_by_imdb_id = lambda _imdb_id: {"tv_results": []}
        self.plugin.chain = types.SimpleNamespace(
            search_medias=lambda **_kwargs: [types.SimpleNamespace(tmdb_id=312575)],
            recognize_media=lambda **_kwargs: wrong_media,
        )

        decision, _media_by_key, attempts = self.plugin._match_tmdb({
            "title": "醉梦",
            "year": "2026",
            "episodes_count": 16,
            "actors": [{"name": "刘诗诗"}, {"name": "胡先煦"}],
            "imdb_id": "tt35288698",
        }, 16)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "low_score")
        self.assertEqual(decision.winner.score, 25)
        self.assertIn("TMDB 未收录 IMDb tt35288698", decision.reason)
        self.assertEqual(attempts[0]["mode"], "imdb_exact")

    def test_subscription_notification_setting_is_forwarded(self) -> None:
        mediainfo = types.SimpleNamespace(
            tmdb_id=654,
            title="通知测试剧",
            year="2026",
        )

        self.plugin._notify_subscription = True
        self.plugin._create_subscription(
            mediainfo=mediainfo,
            douban_id="987",
            season=1,
            total_episode=12,
            category="domestic",
            source_key="douban:987",
        )
        self.assertTrue(FakeSubscribeChain.add_calls[-1]["message"])

        self.plugin._notify_subscription = False
        self.plugin._create_subscription(
            mediainfo=mediainfo,
            douban_id="988",
            season=2,
            total_episode=12,
            category="domestic",
            source_key="douban:988",
        )
        self.assertFalse(FakeSubscribeChain.add_calls[-1]["message"])

    def test_maoyan_rank_payload_becomes_deduplicated_feed_items(self) -> None:
        payload = {
            "dataList": {
                "list": [
                    {
                        "seriesInfo": {
                            "name": "猫眼测试剧",
                            "releaseInfo": "上线10天",
                            "platformDesc": "全网",
                            "seriesId": 12345,
                            "imgUrl": "https://img.test/poster.jpg",
                        },
                    },
                    {
                        "seriesInfo": {
                            "name": "猫眼测试剧",
                            "releaseInfo": "上线10天",
                        },
                    },
                ],
            },
        }
        now = datetime.datetime(2026, 1, 5, 9, 0)

        items = self.plugin._parse_maoyan_items(
            payload=payload,
            list_type="tv",
            source_url="https://piaofang.maoyan.com/test",
            limit=10,
            now=now,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "猫眼测试剧")
        self.assertEqual(items[0].year, "2025")
        self.assertEqual(items[0].guid, "maoyan:tv:12345")
        self.assertIn("movieId=12345", items[0].link)

    def test_sync_can_process_maoyan_without_rss_source(self) -> None:
        self.plugin._rss_urls = ""
        self.plugin._maoyan_enabled = True
        self.plugin._maoyan_types = ["tv"]
        item = plugin_module.FeedItem(
            title="猫眼测试剧",
            guid="maoyan:tv:12345",
            source_url="https://piaofang.maoyan.com/test",
        )
        self.plugin._maoyan_cookies = lambda: {}
        self.plugin._fetch_maoyan_list = lambda *_args, **_kwargs: [item]
        self.plugin._process_item = lambda value: {
            **value.to_dict(),
            "status": "subscribed",
            "subscribe_id": 77,
            "time": "2026-07-27T12:00:00+08:00",
        }

        summary = self.plugin.sync()

        self.assertTrue(summary["success"])
        self.assertEqual(summary["maoyan_lists"], 1)
        self.assertEqual(summary["subscribed"], 1)
        self.assertIn(item.key, self.plugin.get_data("processed_items"))

    def test_douban_rate_limit_has_distinct_status(self) -> None:
        item = plugin_module.FeedItem(
            title="南部档案",
            guid="maoyan:tv:1",
            source_url="https://piaofang.maoyan.com/test",
            year="2026",
        )
        self.plugin.chain = types.SimpleNamespace(
            match_doubaninfo=lambda **_kwargs: (_ for _ in ()).throw(
                LimitException("限流期间，跳过调用")
            ),
        )

        record = self.plugin._process_item(item)

        self.assertEqual(record["status"], "douban_rate_limited")
        self.assertIn("下次执行", record["reason"])

    def test_source_batch_stops_after_douban_rate_limit(self) -> None:
        items = [
            plugin_module.FeedItem(title="条目一", guid="maoyan:tv:1"),
            plugin_module.FeedItem(title="条目二", guid="maoyan:tv:2"),
        ]
        calls = []

        def process_item(item):
            calls.append(item.title)
            return {
                **item.to_dict(),
                "status": "douban_rate_limited",
                "reason": "rate limited",
            }

        self.plugin._process_item = process_item
        summary = {
            "items": 0,
            "subscribed": 0,
            "existing": 0,
            "skipped": 0,
            "failed": 0,
        }

        stopped = self.plugin._process_source_items(
            items=items,
            history=[],
            processed_items={},
            completed_keys=set(),
            summary=summary,
        )

        self.assertTrue(stopped)
        self.assertEqual(calls, ["条目一"])
        self.assertEqual(summary["items"], 1)
        self.assertEqual(summary["failed"], 1)

    def test_douban_search_removes_quotes_and_retries_without_year(self) -> None:
        item = plugin_module.FeedItem(
            title="二龙湖·“村”暖花开3",
            guid="maoyan:tv:3",
            year="2026",
        )
        search_calls = []

        def match_doubaninfo(**kwargs):
            search_calls.append(kwargs)
            if kwargs["name"] == "二龙湖·村暖花开3" and kwargs["year"] is None:
                return {"id": "123456"}
            return None

        self.plugin.chain = types.SimpleNamespace(
            match_doubaninfo=match_doubaninfo,
            douban_info=lambda **_kwargs: {
                "id": "123456",
                "title": "二龙湖·村暖花开3",
            },
        )

        with patch.object(plugin_module.time, "sleep"):
            result = self.plugin._resolve_douban(item)

        self.assertEqual(result["id"], "123456")
        self.assertEqual(
            [
                (call["name"], call["year"], call["season"])
                for call in search_calls
            ],
            [
                ("二龙湖·“村”暖花开3", "2026", None),
                ("二龙湖·村暖花开3", "2026", None),
                ("二龙湖·“村”暖花开3", None, None),
                ("二龙湖·村暖花开3", None, None),
            ],
        )
        self.assertTrue(all(call["raise_exception"] for call in search_calls))

    def test_douban_search_uses_base_title_and_explicit_season(self) -> None:
        cases = (
            ("中餐厅 第十季", "中餐厅", 10, "37814458"),
            ("半熟恋人 第五季", "半熟恋人", 5, "37815127"),
        )

        for source_title, base_title, season, douban_id in cases:
            with self.subTest(title=source_title):
                item = plugin_module.FeedItem(
                    title=source_title,
                    guid=f"maoyan:tv:{douban_id}",
                    year="2026",
                )
                search_calls = []

                def match_doubaninfo(**kwargs):
                    search_calls.append(kwargs)
                    if (
                        kwargs["name"] == base_title
                        and kwargs["year"] == "2026"
                        and kwargs["season"] == season
                    ):
                        return {"id": douban_id}
                    return None

                self.plugin.chain = types.SimpleNamespace(
                    match_doubaninfo=match_doubaninfo,
                    douban_info=lambda **_kwargs: {
                        "id": douban_id,
                        "title": source_title,
                    },
                )

                with patch.object(plugin_module.time, "sleep"):
                    result = self.plugin._resolve_douban(item)

                self.assertEqual(result["id"], douban_id)
                self.assertEqual(
                    (
                        search_calls[0]["name"],
                        search_calls[0]["year"],
                        search_calls[0]["season"],
                    ),
                    (base_title, "2026", season),
                )

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
