"""Category layout tests for the current MoviePilot container mappings."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_layout_tests"


def load_layout_module():
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(PLUGIN_DIR)]
    sys.modules[PACKAGE] = package
    name = f"{PACKAGE}.layout"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / "layout.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


layout = load_layout_module()


class LibraryLayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        defaults = layout.default_layout_config()
        self.layout = layout.LibraryLayout.from_config(
            defaults["inventory_root"],
            defaults["source_routes"],
        )

    def test_current_moviepilot_paths_are_preconfigured(self) -> None:
        self.assertEqual(self.layout.inventory_root, "/SSD/云盘/strm/影视库")
        self.assertEqual(self.layout.media_group("tv"), "series")
        self.assertEqual(self.layout.media_group("movie"), "movie")
        self.assertEqual(self.layout.config_errors, [])

    def test_up_route_uses_media_type_for_all_categories(self) -> None:
        movie = self.layout.plan(
            "/MP/downloads/movie.mkv",
            "实验电影",
            [{"relative_path": "电影 (2026)/电影 (2026).mkv", "size": 4}],
            media_type="movie",
        )
        documentary = self.layout.plan(
            "/MP/downloads/doc/S01E01.mkv",
            "纪录片",
            [{"relative_path": "纪录片 (2026)/Season 01/纪录片 S01E01.mkv", "size": 4}],
            media_type="tv",
        )
        self.assertEqual(movie["link_base"], "/MP/电影UP/实验电影")
        self.assertEqual(documentary["link_base"], "/MP/剧集UP/纪录片")
        self.assertEqual(
            documentary["inventory_base"],
            "/SSD/云盘/strm/影视库/纪录片",
        )

    def test_ssd_route_uses_shared_default_root(self) -> None:
        result = self.layout.plan(
            "/SSD/downloads/show/S01E01.mkv",
            "国产剧",
            [{"relative_path": "剧名 (2026)/Season 01/剧名 S01E01.mkv", "size": 4}],
            media_type="tv",
        )
        self.assertEqual(result["source_route"]["name"], "SSD")
        self.assertEqual(result["link_base"], "/SSD/云盘/l/国产剧")
        self.assertEqual(
            result["inventory_files"][0]["path"],
            "/SSD/云盘/strm/影视库/国产剧/剧名 (2026)/Season 01/剧名 S01E01.strm",
        )
        self.assertEqual(
            result["link_files"][0]["path"],
            "/SSD/云盘/l/国产剧/剧名 (2026)/Season 01/剧名 S01E01.mkv",
        )

    def test_prefix_matching_respects_path_boundaries_and_longest_match(self) -> None:
        configured = layout.LibraryLayout.from_config(
            "/library",
            [
                {
                    "name": "base",
                    "prefix": "/SSD",
                    "link_roots": {"default": "/base"},
                    "enabled": True,
                },
                {
                    "name": "nested",
                    "prefix": "/SSD/fast",
                    "link_roots": {"default": "/nested"},
                    "enabled": True,
                },
            ],
        )
        self.assertEqual(configured.select_route("/SSD/fast/a.mkv").name, "nested")
        self.assertIsNone(configured.select_route("/SSD2/a.mkv"))

    def test_unsafe_category_does_not_create_a_directory(self) -> None:
        result = self.layout.plan(
            "/MP/downloads/other.mkv",
            "../未配置分类",
            [{"relative_path": "Other/Other.mkv", "size": 4}],
            media_type="movie",
        )
        self.assertEqual(result["inventory_base"], "")
        self.assertEqual(result["link_base"], "")
        self.assertTrue(result["errors"])

    def test_structured_config_accepts_json_strings(self) -> None:
        defaults = layout.default_layout_config()
        configured = layout.LibraryLayout.from_config(
            defaults["inventory_root"],
            json.dumps(defaults["source_routes"], ensure_ascii=False),
        )
        result = configured.plan(
            "/MP/downloads/movie.mkv",
            "华语电影",
            [{"relative_path": "电影 (2026)/电影 (2026).mkv", "size": 4}],
            media_type="movie",
        )
        self.assertEqual(configured.config_errors, [])
        self.assertEqual(result["link_base"], "/MP/电影UP/华语电影")


if __name__ == "__main__":
    unittest.main()
