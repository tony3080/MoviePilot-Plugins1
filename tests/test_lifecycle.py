"""Host-isolated tests for the managed subscription lifecycle."""

import importlib.util
import json
import sys
import types
import unittest
from enum import Enum
from pathlib import Path


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
        self.total_episode = 40
        self.lack_episode = 0
        self.manual_total_episode = 1
        self.state = "R"
        self.username = username


class FakeSubscribeOper:
    records = {}

    def get(self, subscribe_id):
        return self.records.get(int(subscribe_id))

    def update(self, subscribe_id, payload):
        subscribe = self.get(subscribe_id)
        if subscribe:
            for key, value in payload.items():
                setattr(subscribe, key, value)
        return subscribe


class FakeSubscribeChain:
    search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)


class ManagedSubscriptionLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeSubscribeOper.records = {}
        FakeSubscribeChain.search_calls = []
        plugin_module.SubscribeOper = FakeSubscribeOper
        plugin_module.SubscribeChain = FakeSubscribeChain
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

    def test_completion_pauses_card_and_increased_total_resumes_search(self) -> None:
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

    def test_unchanged_total_switches_to_100_and_manual_review(self) -> None:
        subscribe = FakeSubscribe(2)
        self._complete(subscribe)
        self._make_due(2)
        self.plugin.chain = types.SimpleNamespace(
            douban_info=lambda **_kwargs: {"episodes_count": 40},
        )

        summary = self.plugin._process_due_confirmations()

        self.assertEqual(summary["manual_review"], 1)
        self.assertEqual(subscribe.total_episode, 100)
        self.assertEqual(subscribe.lack_episode, 60)
        self.assertEqual(subscribe.state, "S")
        self.assertEqual(self.plugin._managed_record(2)["status"], "manual_review")
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


if __name__ == "__main__":
    unittest.main()
