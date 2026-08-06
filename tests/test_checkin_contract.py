"""Static repository checks for the Checkin MoviePilot V2 plugin."""

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "package.v2.json"
PLUGIN_ID = "Checkin"
PLUGIN_DIR = ROOT / "plugins.v2" / "checkin"
INIT_PATH = PLUGIN_DIR / "__init__.py"


class CheckinContractTest(unittest.TestCase):
    def test_runtime_and_market_metadata_match(self) -> None:
        package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        metadata = package[PLUGIN_ID]
        tree = ast.parse(INIT_PATH.read_text(encoding="utf-8"))
        plugin_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == PLUGIN_ID
        )
        attributes = {}
        for item in plugin_class.body:
            if isinstance(item, ast.Assign) and len(item.targets) == 1:
                target = item.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        attributes[target.id] = ast.literal_eval(item.value)
                    except (TypeError, ValueError):
                        pass
        for runtime, market in {
            "plugin_name": "name",
            "plugin_desc": "description",
            "plugin_icon": "icon",
            "plugin_version": "version",
            "plugin_author": "author",
            "auth_level": "level",
        }.items():
            self.assertEqual(attributes[runtime], metadata[market])
        self.assertIn(f"v{metadata['version']}", metadata["history"])

    def test_v2_browser_and_scheduler_contract(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("from app.helper.browser import PlaywrightHelper", source)
        self.assertIn("PlaywrightHelper().action", source)
        self.assertIn('"func_kwargs": {"site": site}', source)
        self.assertIn("def _append_history", source)
        self.assertIn("self.save_data(", source)
        self.assertIn('"history",', source)
        self.assertNotIn("settings.yaml", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("def get_sidebar_nav", source)
        self.assertIn("def get_api", source)
        self.assertNotIn("def get_render_mode", source)
        self.assertIn("def get_page", source)
        self.assertIn("VDataTableVirtual", source)

    def test_native_config_form_contains_all_controls(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        for model in (
            "enabled",
            "onlyonce",
            "notify",
            "history_days",
            "smzdm_enabled",
            "smzdm_cookie",
            "smzdm_cron",
            "chiphell_enabled",
            "chiphell_cookie",
            "chiphell_cron",
        ):
            self.assertIn(f'"model": "{model}"', source)
        self.assertFalse((PLUGIN_DIR / "src" / "components" / "Config.vue").exists())
        self.assertFalse((PLUGIN_DIR / "dist" / "assets" / "remoteEntry.js").exists())
        self.assertFalse((PLUGIN_DIR / "package.json").exists())
        self.assertNotIn('"title": "签到历史"', source.split("def get_page", 1)[0])


if __name__ == "__main__":
    unittest.main()
