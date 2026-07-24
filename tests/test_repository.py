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


if __name__ == "__main__":
    unittest.main()
