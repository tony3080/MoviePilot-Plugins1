"""Tests for qB source naming kept separate from MP hardlink naming."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_rss_rename_tests"


def load_package_module(name):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


rss_rename = load_package_module("rss_rename")


class RenameRuleTest(unittest.TestCase):
    def test_global_regex_can_replace_brackets_with_empty_text(self):
        rules = rss_rename.parse_rename_rules(r"/[\[\]]/g =>")

        self.assertEqual(rules[0].apply("[Movie].[2026].mkv"), "Movie.2026.mkv")

    def test_regular_and_regex_rules_keep_configuration_order(self):
        rules = rss_rename.parse_rename_rules(
            "BluRay => REMUX\n/UHD/i => U版"
        )

        value = "Movie.UHD.BluRay.mkv"
        for rule in rules:
            value = rule.apply(value)
        self.assertEqual(value, "Movie.U版.REMUX.mkv")


class ChineseTitleTest(unittest.TestCase):
    def test_extracts_chinese_candidate_from_rss_title(self):
        title = "<![CDATA[[沙丘：第二部 / Dune: Part Two][2160p][REMUX]]]>"
        self.assertEqual(rss_rename.extract_chinese_title(title), "沙丘：第二部")

    def test_skips_noise_brackets_until_meaningful_chinese_title(self):
        title = "[国语][特效][REMUX][沙丘：第二部]"
        self.assertEqual(rss_rename.extract_chinese_title(title), "沙丘：第二部")

    def test_labels_do_not_block_chinese_prefix(self):
        self.assertFalse(rss_rename.has_meaningful_chinese("Movie-国配-特效.mkv"))
        self.assertTrue(rss_rename.has_meaningful_chinese("[沙丘].Movie.mkv"))


class RenamePlanTest(unittest.TestCase):
    def test_files_are_planned_before_deep_to_shallow_directories(self):
        rules = rss_rename.parse_rename_rules("BluRay => REMUX-U版")
        file_ops, directory_ops = rss_rename.build_rename_plan(
            [{"index": 0, "name": "Dune/BluRay/Movie.BluRay.mkv", "size": 1}],
            rules=rules,
            chinese_title="沙丘：第二部",
            add_cn=True,
            add_fx=True,
        )

        self.assertEqual(file_ops, [(
            "Dune/BluRay/Movie.BluRay.mkv",
            "Dune/BluRay/[沙丘：第二部].Movie-国配-特效-REMUX-U版.mkv",
        )])
        self.assertEqual(directory_ops, [
            (
                "Dune/BluRay",
                "Dune/[沙丘：第二部]-国配-特效-REMUX-U版",
            ),
            ("Dune", "[沙丘：第二部].Dune-国配-特效"),
        ])

    def test_existing_markers_are_normalized_before_remux(self):
        value = rss_rename.transform_name(
            "Movie-REMUX-U版-国配-特效.mkv",
            is_file=True,
        )
        self.assertEqual(value, "Movie-国配-特效-REMUX-U版.mkv")

    def test_rule_replacement_is_used_as_marker_anchor_without_remux(self):
        value = rss_rename.transform_name(
            "Movie.V2.mkv",
            is_file=True,
            rules=rss_rename.parse_rename_rules("V2 => U版"),
            add_cn=True,
            add_fx=True,
        )
        self.assertEqual(value, "Movie-国配-特效-U版.mkv")

    def test_preflight_rejects_target_that_is_already_another_file(self):
        rules = rss_rename.parse_rename_rules("A.mkv => B.mkv")
        with self.assertRaises(rss_rename.RssRenameError):
            rss_rename.build_rename_plan(
                [{"name": "A.mkv"}, {"name": "B.mkv"}],
                rules=rules,
                chinese_title="",
                add_cn=False,
                add_fx=False,
            )


class RenameExecutionTest(unittest.TestCase):
    def test_executor_renames_files_then_directories_and_rereads(self):
        class Gateway:
            def __init__(self):
                self.calls = []
                self.reads = 0

            def list_torrent_files(self, _server, _info_hash):
                self.reads += 1
                if self.reads == 1:
                    return [{"index": 0, "name": "Root/Movie.mkv", "size": 1}]
                return [{"index": 0, "name": "[电影].Root/[电影].Movie.mkv", "size": 1}]

            def rename_torrent_file(self, _server, _hash, old, new):
                self.calls.append(("file", old, new))

            def rename_torrent_folder(self, _server, _hash, old, new):
                self.calls.append(("folder", old, new))

        gateway = Gateway()
        result = rss_rename.QbSourceRenameService(gateway).apply(
            object(),
            "abc123",
            rss_title="[电影 / Movie][2026]",
            rename_enabled=False,
            rename_rules="",
            add_chinese_title=True,
        )

        self.assertEqual(result["status"], "renamed")
        self.assertEqual([call[0] for call in gateway.calls], ["file", "folder"])
        self.assertEqual(result["final_files"][0]["name"], "[电影].Root/[电影].Movie.mkv")


if __name__ == "__main__":
    unittest.main()
