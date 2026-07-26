"""Static checks for the MoviePilot plugin repository contract."""

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "package.v2.json"
PLUGIN_ID = "DoubanSubscribe"
PLUGIN_DIR = ROOT / "plugins.v2" / PLUGIN_ID.lower()
INIT_PATH = PLUGIN_DIR / "__init__.py"


def class_attributes(path: Path, class_name: str) -> dict:
    """Read literal class attributes without importing MoviePilot."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            result = {}
            for item in node.body:
                if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                    continue
                target = item.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        result[target.id] = ast.literal_eval(item.value)
                    except (ValueError, TypeError):
                        continue
            return result
    raise AssertionError(f"Missing plugin class: {class_name}")


class RepositoryContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        self.metadata = self.package[PLUGIN_ID]
        self.attributes = class_attributes(INIT_PATH, PLUGIN_ID)

    def test_official_v2_layout(self) -> None:
        self.assertTrue(INIT_PATH.is_file())
        self.assertEqual(PLUGIN_DIR.name, PLUGIN_ID.lower())

    def test_required_market_metadata(self) -> None:
        required = {
            "name",
            "description",
            "version",
            "icon",
            "author",
            "level",
            "history",
        }
        self.assertFalse(required - self.metadata.keys())
        self.assertIn(self.metadata["level"], {1, 2, 3})
        self.assertIs(self.metadata.get("v2"), True)
        self.assertEqual(self.metadata.get("system_version"), ">=2.15.0")

    def test_runtime_metadata_matches_market(self) -> None:
        mappings = {
            "plugin_name": "name",
            "plugin_desc": "description",
            "plugin_icon": "icon",
            "plugin_version": "version",
            "plugin_author": "author",
            "auth_level": "level",
        }
        for runtime_key, market_key in mappings.items():
            self.assertEqual(
                self.attributes[runtime_key],
                self.metadata[market_key],
                f"{runtime_key} must match {market_key}",
            )

    def test_release_history_contains_current_version(self) -> None:
        version_key = f"v{self.metadata['version']}"
        self.assertIn(version_key, self.metadata["history"])

    def test_locked_douban_episode_contract(self) -> None:
        tree = ast.parse(INIT_PATH.read_text(encoding="utf-8"), filename=str(INIT_PATH))
        add_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add"
            and any(keyword.arg == "manual_total_episode" for keyword in node.keywords)
        ]
        self.assertEqual(len(add_calls), 1, "expected one locked subscription creation call")
        keywords = {keyword.arg: keyword.value for keyword in add_calls[0].keywords}
        required = {
            "tmdbid",
            "doubanid",
            "season",
            "total_episode",
            "lack_episode",
            "manual_total_episode",
        }
        self.assertFalse(required - keywords.keys())
        self.assertEqual(ast.literal_eval(keywords["manual_total_episode"]), 1)
        self.assertIsInstance(keywords["total_episode"], ast.Name)
        self.assertEqual(keywords["total_episode"].id, "total_episode")
        self.assertIsInstance(keywords["lack_episode"], ast.Name)
        self.assertEqual(keywords["lack_episode"].id, "total_episode")

    def test_completion_takeover_and_settings_contract(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("ChainEventType.SubscribeCompletionCheck", source)
        self.assertIn('== PLUGIN_USERNAME', source)
        self.assertIn('"state": "S"', source)
        self.assertIn('"model": "confirmation_days"', source)
        self.assertIn('"model": "media_categories"', source)
        self.assertNotIn('"model": "minimum_score"', source)
        self.assertNotIn('"model": "minimum_margin"', source)

    def test_detail_page_uses_supported_virtual_tables(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn('"component": "VDataTableVirtual"', source)
        self.assertNotIn('"component": "VDataTable"', source)

    def test_history_search_and_durable_dedup_contract(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn('"path": "/history/search"', source)
        self.assertIn("RECENT_HISTORY_LIMIT = 50", source)
        self.assertIn('self.save_data("processed_items"', source)
        self.assertNotIn("history[-500:]", source)

    def test_unknown_total_periodic_resolution_contract(self) -> None:
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("UNKNOWN_TOTAL_EPISODE = 100", source)
        self.assertIn('"status": "awaiting_douban_total"', source)
        self.assertIn("def _process_pending_totals", source)
        self.assertIn('"total_pending": False', source)


if __name__ == "__main__":
    unittest.main()
