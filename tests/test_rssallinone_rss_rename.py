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

    def test_trims_unseparated_technical_suffix_from_chinese_title(self):
        title = (
            "Rouge 1987 CHN BluRay Remux UHD-CHD"
            "[胭脂扣  国版原盘REMUX  国粤双语  简体中文字幕]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "胭脂扣")

    def test_keeps_spaced_title_when_suffix_is_not_technical(self):
        self.assertEqual(
            rss_rename.extract_chinese_title("[新  龙门客栈 / New Dragon Gate Inn]"),
            "新  龙门客栈",
        )

    def test_labels_do_not_block_chinese_prefix(self):
        self.assertFalse(rss_rename.has_meaningful_chinese("Movie-国配-特效.mkv"))
        self.assertTrue(rss_rename.has_meaningful_chinese("[沙丘].Movie.mkv"))

    def test_technical_chinese_labels_do_not_count_as_a_title(self):
        self.assertFalse(rss_rename.has_meaningful_chinese(
            "Movie.REMUX.杜比视界.高帧率.简体中文字幕.C版.mkv"
        ))

    def test_technical_rule_replacements_do_not_block_chinese_prefix(self):
        value = rss_rename.transform_name(
            "Movie.DoVi.HFR.mkv",
            is_file=True,
            rules=rss_rename.parse_rename_rules(
                "DoVi => 杜比视界\nHFR => 高帧率"
            ),
            chinese_title="沙丘：第二部",
        )

        self.assertEqual(
            value,
            "[沙丘：第二部].Movie.杜比视界.高帧率.mkv",
        )

    def test_technical_brackets_are_not_selected_as_rss_title(self):
        title = "[杜比视界][高帧率][简体中文字幕][沙丘：第二部 / Dune]"
        self.assertEqual(rss_rename.extract_chinese_title(title), "沙丘：第二部")

    def test_extracts_ubits_title_before_subtitle_slashes(self):
        title = (
            "Sentimental Value 2025 Criterion Collection UHD BluRay "
            "2160p REMUX-UBits[情感价值 CC标准收藏版 4K UHD原盘 REMUX "
            "简体/繁体/简英双语/繁英双语]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "情感价值")

    def test_extracts_ubits_title_before_single_spaced_technical_text(self):
        title = (
            "An American Affair 2009 USA BluRay-UBits"
            "[美国情事 蓝光原盘 REMUX 简体/繁体/简英双语/繁英双语]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "美国情事")

    def test_removes_ubits_release_counter_badge(self):
        title = (
            "Tom Jones 1963 CC BluRay-UBits"
            "[【原盘Remux 00139】汤姆·琼斯 / 汤姆琼斯 CC标准收藏版]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "汤姆·琼斯")

    def test_extracts_ubits_title_before_type_section(self):
        title = (
            "Kneecap 2024 BluRay-UBits"
            "[膝盖骨乐队 | 类型：剧情 喜剧 英版原盘 REMUX 内封简繁字幕]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "膝盖骨乐队")

    def test_extracts_ubits_title_before_regional_edition(self):
        title = (
            "What Dreams May Come 1998 UHD BluRay-UBits"
            "[美梦成真 美Shout Factory版 4K UHD原盘 REMUX 简体/繁体]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "美梦成真")

    def test_extracts_chd_title_before_descriptive_regional_edition(self):
        title = (
            "Sense and Sensibility 1995 USA 30th Anniv V2 BluRay-CHD"
            "[理智与情感 美三十周年纪念版原盘REMUX "
            "国{东方联合VCD}英双语 简繁双语四字幕]"
        )

        self.assertEqual(rss_rename.extract_chinese_title(title), "理智与情感")


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

    def test_remove_cn_marker_preserves_effects_and_extension(self):
        value = rss_rename.transform_name(
            "Movie-国配-特效-REMUX-U版.mkv",
            is_file=True,
            remove_cn=True,
        )
        self.assertEqual(value, "Movie-特效-REMUX-U版.mkv")

    def test_remove_cn_marker_can_remove_only_marker(self):
        value = rss_rename.transform_name(
            "Movie-国配.mkv",
            is_file=True,
            remove_cn=True,
        )
        self.assertEqual(value, "Movie.mkv")

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
                self.files = [{"index": 0, "name": "Root/Movie.mkv", "size": 1}]

            def list_torrent_files(self, _server, _info_hash):
                return self.files

            def rename_torrent_file(self, _server, _hash, old, new):
                self.calls.append(("file", old, new))
                self.files[0]["name"] = new

            def rename_torrent_folder(self, _server, _hash, old, new):
                self.calls.append(("folder", old, new))
                prefix = f"{old}/"
                self.files[0]["name"] = (
                    f"{new}/{self.files[0]['name'][len(prefix):]}"
                )

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

    def test_executor_waits_for_file_rename_before_renaming_folder(self):
        class Gateway:
            def __init__(self):
                self.calls = []
                self.files = [{"index": 0, "name": "Root-CHD/Movie-CHD.mkv"}]
                self.pending_file = None
                self.file_polls = 0

            def list_torrent_files(self, _server, _info_hash):
                if self.pending_file:
                    self.file_polls += 1
                    if self.file_polls >= 3:
                        self.files[0]["name"] = self.pending_file
                        self.pending_file = None
                return self.files

            def rename_torrent_file(self, _server, _hash, old, new):
                self.calls.append(("file", old, new))
                self.pending_file = new

            def rename_torrent_folder(self, _server, _hash, old, new):
                self.calls.append(("folder", old, new))
                prefix = f"{old}/"
                self.files[0]["name"] = (
                    f"{new}/{self.files[0]['name'][len(prefix):]}"
                )

        gateway = Gateway()
        result = rss_rename.QbSourceRenameService(
            gateway, sleeper=lambda _seconds: None
        ).apply(
            object(),
            "abc123",
            rss_title="",
            rename_enabled=True,
            rename_rules="CHD => REMUX-C版",
            add_chinese_title=False,
        )

        self.assertEqual(result["status"], "renamed")
        self.assertEqual([call[0] for call in gateway.calls], ["file", "folder"])
        self.assertEqual(
            result["final_files"][0]["name"],
            "Root-REMUX-C版/Movie-REMUX-C版.mkv",
        )

    def test_executor_fails_when_qb_reports_success_without_applying_rename(self):
        class Gateway:
            files = [{"index": 0, "name": "Movie-CHD.mkv"}]

            def list_torrent_files(self, _server, _info_hash):
                return self.files

            @staticmethod
            def rename_torrent_file(_server, _hash, _old, _new):
                return None

            @staticmethod
            def rename_torrent_folder(*_args):
                return None

        result = rss_rename.QbSourceRenameService(
            Gateway(), sleeper=lambda _seconds: None
        ).apply(
            object(),
            "abc123",
            rss_title="",
            rename_enabled=True,
            rename_rules="CHD => REMUX-C版",
            add_chinese_title=False,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("改名未落地", result["error"])

    def test_marker_stage_uses_verified_base_name_and_keeps_fixed_order(self):
        class Gateway:
            def __init__(self):
                self.files = [{"index": 0, "name": "Root-CHD/Movie-CHD.mkv"}]

            def list_torrent_files(self, _server, _info_hash):
                return self.files

            def rename_torrent_file(self, _server, _hash, old, new):
                for item in self.files:
                    if item["name"] == old:
                        item["name"] = new

            def rename_torrent_folder(self, _server, _hash, old, new):
                prefix = f"{old}/"
                for item in self.files:
                    if item["name"].startswith(prefix):
                        item["name"] = f"{new}/{item['name'][len(prefix):]}"

        gateway = Gateway()
        service = rss_rename.QbSourceRenameService(
            gateway, sleeper=lambda _seconds: None
        )
        base = service.apply(
            object(),
            "abc123",
            rss_title="[电影 / Movie]",
            rename_enabled=True,
            rename_rules="CHD => REMUX-C版",
            add_chinese_title=True,
        )
        markers = service.apply(
            object(),
            "abc123",
            rss_title="",
            rename_enabled=False,
            rename_rules="",
            add_chinese_title=False,
            add_cn=True,
            add_fx=True,
        )

        self.assertEqual(base["status"], "renamed")
        self.assertEqual(markers["status"], "renamed")
        self.assertEqual(
            markers["final_files"][0]["name"],
            "[电影].Root-国配-特效-REMUX-C版/"
            "[电影].Movie-国配-特效-REMUX-C版.mkv",
        )

    def test_executor_waits_for_qb_file_list_before_renaming(self):
        class Gateway:
            def __init__(self):
                self.reads = 0
                self.calls = []
                self.current_name = "Movie.mkv"

            def list_torrent_files(self, _server, _info_hash):
                self.reads += 1
                if self.reads < 3:
                    return []
                return [{"index": 0, "name": self.current_name, "size": 1}]

            def rename_torrent_file(self, _server, _hash, old, new):
                self.calls.append((old, new))
                self.current_name = new

            def rename_torrent_folder(self, *_args):
                raise AssertionError("single-file torrent has no folder rename")

        sleeps = []
        gateway = Gateway()
        result = rss_rename.QbSourceRenameService(
            gateway, sleeper=sleeps.append
        ).apply(
            object(),
            "abc123",
            rss_title="[电影 / Movie][2026]",
            rename_enabled=False,
            rename_rules="",
            add_chinese_title=True,
        )

        self.assertEqual(result["status"], "renamed")
        self.assertEqual(sleeps, [1, 1])
        self.assertEqual(gateway.calls, [("Movie.mkv", "[电影].Movie.mkv")])


if __name__ == "__main__":
    unittest.main()
