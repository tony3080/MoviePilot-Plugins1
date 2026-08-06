"""Runtime-oriented tests using a fake MoviePilot CloakBrowser adapter."""

import importlib.util
import sys
import types
import unittest
from abc import ABCMeta, abstractmethod
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "checkin"


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _PluginBase(metaclass=ABCMeta):
    def __init__(self, *args, **kwargs):
        self._test_data = {}
        self._test_config = {}
        self._test_messages = []

    @abstractmethod
    def init_plugin(self, config=None):
        pass

    @abstractmethod
    def get_state(self):
        pass

    @abstractmethod
    def get_api(self):
        pass

    @abstractmethod
    def get_form(self):
        pass

    @abstractmethod
    def get_page(self):
        pass

    @staticmethod
    def get_render_mode():
        return "vuetify", None

    def get_data(self, key):
        return self._test_data.get(key)

    def save_data(self, key, value):
        self._test_data[key] = value

    def update_config(self, value):
        self._test_config = value

    def post_message(self, **kwargs):
        self._test_messages.append(kwargs)


class _NotificationType:
    Plugin = "plugin"


class _CronTrigger:
    @staticmethod
    def from_crontab(value):
        return ("cron", value)


class _FakeContext:
    def cookies(self):
        return [{"name": "B7Y9_auth", "value": "valid"}]


class _FakePage:
    def __init__(self, response):
        self.response = response
        self.context = _FakeContext()
        self.headers = {}
        self.url = ""

    def set_extra_http_headers(self, headers):
        self.headers.update(headers)

    def goto(self, url, *args, **kwargs):
        self.url = url

    def inner_text(self, _selector):
        return self.response

    def content(self):
        return self.response

    def evaluate(self, _script, _argument=None):
        return self.response


def _load_plugin_module():
    app = types.ModuleType("app")
    app.__path__ = []
    app_log = types.ModuleType("app.log")
    app_log.logger = _Logger()
    app_plugins = types.ModuleType("app.plugins")
    app_plugins._PluginBase = _PluginBase
    app_schemas = types.ModuleType("app.schemas")
    app_schemas.__path__ = []
    app_types = types.ModuleType("app.schemas.types")
    app_types.NotificationType = _NotificationType
    apscheduler = types.ModuleType("apscheduler")
    apscheduler.__path__ = []
    apscheduler_triggers = types.ModuleType("apscheduler.triggers")
    apscheduler_triggers.__path__ = []
    apscheduler_cron = types.ModuleType("apscheduler.triggers.cron")
    apscheduler_cron.CronTrigger = _CronTrigger
    modules = {
        "app": app,
        "app.log": app_log,
        "app.plugins": app_plugins,
        "app.schemas": app_schemas,
        "app.schemas.types": app_types,
        "apscheduler": apscheduler,
        "apscheduler.triggers": apscheduler_triggers,
        "apscheduler.triggers.cron": apscheduler_cron,
    }
    originals = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)

    try:
        name = "checkin_runtime_plugin"
        spec = importlib.util.spec_from_file_location(
            name,
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for module_name, original in originals.items():
            if original is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original


class CheckinRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_plugin_module()

    def setUp(self):
        self.browser_calls = []
        self.plugin = self.module.Checkin()
        self.plugin.init_plugin({
            "notify": True,
            "smzdm_cookie": "smzdm_token=secret-one",
            "chiphell_cookie": "B7Y9_auth=secret-two",
        })

        def browser_action(url, cookie, callback, ua=None):
            self.browser_calls.append({"url": url, "cookies": cookie, "ua": ua})
            if "smzdm.com" in url:
                response = (
                    '{"error_code":0,"error_msg":"签到成功",'
                    '"data":{"checkin":{"daily_num":"9","cpoints":"3"}}}'
                )
            else:
                response = (
                    '<strong class="vwmy"><a>tester</a></strong>'
                    '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
                    '<span>积分: 888</span>'
                )
            return callback(_FakePage(response))

        self.plugin._browser_action = browser_action

    def test_smzdm_browser_result_is_persisted_without_cookie(self):
        record = self.plugin._run_site("smzdm", manual=True)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["days"], "9")
        self.assertEqual(len(self.plugin.get_data("history")), 1)
        self.assertEqual(len(self.plugin._test_messages), 1)
        self.assertEqual(self.browser_calls[0]["cookies"], "smzdm_token=secret-one")
        self.assertIn("api.smzdm.com", self.browser_calls[0]["url"])
        self.assertNotIn("secret-one", repr(self.plugin.get_data("history")))

    def test_smzdm_info_response_supplies_continuous_days(self):
        page = _FakePage({
            "checkin": '{"error_code":1,"error_msg":"已签到"}',
            "info": '{"data":{"daily_attendance_number":"27"}}',
        })
        result = self.module.Checkin._smzdm_api_handler(page)
        self.assertEqual(result["status"], "already")
        self.assertEqual(result["days"], "27")

    def test_chiphell_browser_result_extracts_account_summary(self):
        record = self.plugin._run_site("chiphell", manual=False)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["username"], "tester")
        self.assertEqual(record["points"], "888")
        self.assertNotIn("streak_days", record)
        self.assertEqual(record["trigger"], "scheduled")
        self.assertNotIn("secret-two", repr(self.plugin.get_data("history")))

    def test_smzdm_falls_back_to_web_endpoint_when_mobile_api_fails(self):
        calls = []

        def browser_action(url, cookie, callback, ua=None):
            calls.append(url)
            if "api.smzdm.com" in url:
                response = '{"error_code":"11111","error_msg":"请先登录"}'
            else:
                response = '{"error_code":0,"error_msg":"签到成功"}'
            return callback(_FakePage(response))

        self.plugin._browser_action = browser_action
        record = self.plugin._run_site("smzdm", manual=True)
        self.assertEqual(record["status"], "success")
        self.assertEqual(len(calls), 2)
        self.assertIn("api.smzdm.com", calls[0])
        self.assertIn("zhiyou.smzdm.com", calls[1])

    def test_native_form_is_nonempty_and_contains_all_models(self):
        self.assertFalse(self.plugin.__class__.__abstractmethods__)
        form, defaults = self.plugin.get_form()
        self.assertTrue(form)
        self.assertEqual(form[0]["component"], "VForm")

        models = set()

        def walk(value):
            if isinstance(value, dict):
                model = (value.get("props") or {}).get("model")
                if model:
                    models.add(model)
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(form)
        self.assertEqual(models, set(defaults))
        self.assertNotIn("VDataTableVirtual", repr(form))

    def test_form_includes_recent_history_rows(self):
        self.plugin._test_data["history"] = [{
            "date": "2026-08-06 12:32:57",
            "site": "chiphell",
            "site_name": "Chiphell",
            "status": "success",
            "message": "论坛页访问成功，登录态有效",
            "points": "1234",
            "trigger": "manual",
        }]
        page = self.plugin.get_page()
        table = page[0]["content"][0]["content"][0]
        self.assertEqual(table["component"], "VDataTableVirtual")
        self.assertEqual(table["props"]["items"][0]["site_name"], "Chiphell")
        self.assertEqual(table["props"]["items"][0]["trigger_label"], "手动")
        self.assertEqual(table["props"]["items"][0]["points"], "1234")
        self.assertEqual(table["props"]["items"][0]["streak_days"], "-")

    def test_success_notification_is_sent_even_when_failure_notifications_are_disabled(self):
        self.plugin._notify = False
        record = self.plugin._run_site("chiphell", manual=True)
        self.assertEqual(record["status"], "success")
        self.assertEqual(len(self.plugin._test_messages), 1)

    def test_streak_days_are_calculated_from_successful_history(self):
        self.plugin._test_data["history"] = [
            {
                "date": "2026-08-04 09:00:00",
                "site": "smzdm",
                "status": "success",
            },
            {
                "date": "2026-08-05 09:00:00",
                "site": "smzdm",
                "status": "already",
            },
        ]
        self.plugin._module_now = None
        record = self.plugin._decorate_result(
            "smzdm",
            {"status": "success", "message": "ok"},
            manual=True,
        )
        self.assertEqual(record["streak_days"], 3)


if __name__ == "__main__":
    unittest.main()
