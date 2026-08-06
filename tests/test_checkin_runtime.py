"""Runtime-oriented tests using a fake MoviePilot CloakBrowser adapter."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "checkin"


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _PluginBase:
    def __init__(self, *args, **kwargs):
        self._test_data = {}
        self._test_config = {}
        self._test_messages = []

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
    modules = {
        "app": app,
        "app.log": app_log,
        "app.plugins": app_plugins,
        "app.schemas": app_schemas,
        "app.schemas.types": app_types,
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

        def browser_action(url, cookie, callback):
            self.browser_calls.append({"url": url, "cookies": cookie})
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
        self.assertNotIn("secret-one", repr(self.plugin.get_data("history")))

    def test_chiphell_browser_result_extracts_account_summary(self):
        record = self.plugin._run_site("chiphell", manual=False)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["username"], "tester")
        self.assertEqual(record["points"], "888")
        self.assertEqual(record["trigger"], "scheduled")
        self.assertNotIn("secret-two", repr(self.plugin.get_data("history")))


if __name__ == "__main__":
    unittest.main()
