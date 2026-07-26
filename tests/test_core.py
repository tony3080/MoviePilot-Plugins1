"""Tests for RSS parsing and deterministic media matching."""

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "doubansubscribe" / "core.py"
SPEC = importlib.util.spec_from_file_location("doubansubscribe_core", CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


class FeedParsingTest(unittest.TestCase):
    def test_parses_rsshub_douban_feed(self) -> None:
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>豆瓣热门电视剧</title>
          <item>
            <title>罚罪2</title>
            <link>https://movie.douban.com/subject/37106797/</link>
            <guid>https://movie.douban.com/subject/37106797/</guid>
            <pubDate>Fri, 24 Jul 2026 00:00:00 GMT</pubDate>
            <description>&lt;img src="https://img.example/poster.jpg" /&gt;&lt;p&gt;2025&lt;/p&gt;</description>
          </item>
        </channel></rss>"""
        items = core.parse_feed(xml, "http://rsshub.local/hot_tv")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "罚罪2")
        self.assertEqual(items[0].douban_id, "37106797")
        self.assertEqual(items[0].year, "2025")
        self.assertEqual(items[0].poster, "https://img.example/poster.jpg")
        self.assertEqual(items[0].key, "douban:37106797")

    def test_parses_atom_and_deduplicates_entries(self) -> None:
        xml = """<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>飞常日志2</title><link href="https://movie.douban.com/subject/37261428/"/></entry>
          <entry><title>飞常日志2</title><link href="https://movie.douban.com/subject/37261428/"/></entry>
        </feed>"""
        items = core.parse_feed(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].douban_id, "37261428")


class TitleHypothesisTest(unittest.TestCase):
    def assert_season_candidate(self, title: str, base: str, season: int, strength: str) -> None:
        hypotheses = core.build_title_hypotheses(title)
        self.assertIn(
            (core.normalize_title(base), season, strength),
            {
                (core.normalize_title(item.title), item.season, item.strength)
                for item in hypotheses
            },
        )

    def test_strong_season_markers(self) -> None:
        self.assert_season_candidate("罚罪 第二季", "罚罪", 2, "strong")
        self.assert_season_candidate("罚罪 第2季", "罚罪", 2, "strong")
        self.assert_season_candidate("罚罪 S02", "罚罪", 2, "strong")
        self.assert_season_candidate("罚罪 Season 2", "罚罪", 2, "strong")

    def test_weak_season_markers(self) -> None:
        self.assert_season_candidate("罚罪2", "罚罪", 2, "weak")
        self.assert_season_candidate("罚罪二", "罚罪", 2, "weak")
        self.assert_season_candidate("罚罪 II", "罚罪", 2, "weak")
        self.assert_season_candidate("罚罪 第二部", "罚罪", 2, "weak")

    def test_native_numeric_titles_are_not_split(self) -> None:
        for title in ("神奇女侠1984", "1899", "1923", "24", "三体", "二十不惑"):
            hypotheses = core.build_title_hypotheses(title)
            self.assertEqual(
                [(item.title, item.season, item.mode) for item in hypotheses],
                [(title, None, "exact_title")],
            )

    def test_primary_original_and_alias_titles_become_search_paths(self) -> None:
        hypotheses = core.build_search_hypotheses(
            title="罚罪2",
            original_title="Punishment 2",
            aliases=("罚罪 第二季", "罚罪2"),
        )
        paths = {(item.title, item.season, item.mode) for item in hypotheses}
        self.assertIn(("罚罪2", None, "exact_title"), paths)
        self.assertIn(("Punishment 2", None, "original_title"), paths)
        self.assertIn(("罚罪", 2, "base_and_season"), paths)


class DoubanEpisodeTest(unittest.TestCase):
    def test_prefers_declared_episode_count(self) -> None:
        info = {"episodes_count": 40, "webisode_count": 36, "last_episode_number": 12}
        self.assertEqual(core.extract_total_episode(info), 40)

    def test_parses_episode_info_but_not_current_episode(self) -> None:
        self.assertEqual(core.extract_total_episode({"episodes_info": "全36集"}), 36)
        self.assertIsNone(core.extract_total_episode({"last_episode_number": 12}))

    def test_detects_started_airing_without_treating_progress_as_total(self) -> None:
        today = date(2026, 7, 26)
        self.assertTrue(core.has_started_airing({"is_released": True}, today))
        self.assertTrue(core.has_started_airing({"last_episode_number": 3}, today))
        self.assertTrue(core.has_started_airing({"episodes_info": "更新至第 5 集"}, today))
        self.assertTrue(core.has_started_airing({"pubdate": ["2026-07-20(中国大陆)"]}, today))
        self.assertFalse(core.has_started_airing({"is_released": False}, today))
        self.assertFalse(core.has_started_airing({"is_released": "false"}, today))
        self.assertFalse(core.has_started_airing({"pubdate": ["2026-08-01"]}, today))
        self.assertIsNone(core.extract_total_episode({"last_episode_number": 3}))


class MediaRegionTest(unittest.TestCase):
    def test_classifies_supported_regions_from_douban_countries(self) -> None:
        cases = {
            "domestic": {"countries": ["中国大陆"]},
            "western": {"countries": ["英国", "美国"]},
            "japan_korea": {"countries": ["韩国"]},
            "other": {"countries": ["泰国"]},
        }
        for expected, info in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(core.classify_media_region(info), expected)

    def test_first_recognized_country_controls_mixed_production(self) -> None:
        self.assertEqual(
            core.classify_media_region({"countries": ["美国", "日本"]}),
            "western",
        )

    def test_card_subtitle_is_used_when_country_list_is_missing(self) -> None:
        self.assertEqual(
            core.classify_media_region({"card_subtitle": "2026 / 日本 / 剧情"}),
            "japan_korea",
        )


class CandidateScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = {
            "title": "罚罪2",
            "original_title": "罚罪 第二季",
            "aliases": ["罚罪 第二季"],
            "year": "2025",
            "total_episode": 40,
            "actors": ["黄景瑜", "王传君"],
            "directors": ["天毅"],
        }

    def test_internal_match_thresholds_are_fixed(self) -> None:
        self.assertEqual(core.MATCH_ACCEPT_SCORE, 80)
        self.assertEqual(core.MATCH_MIN_LEAD, 15)

    def test_parent_season_beats_duplicate_standalone_entry(self) -> None:
        parent = core.TmdbCandidate(
            tmdb_id=208919,
            title="罚罪",
            names=("罚罪2", "罚罪 第二季"),
            year="2022",
            season=2,
            season_year="2025",
            season_episode_count=40,
            actors=("黄景瑜", "王传君"),
            directors=("天毅",),
            mode="base_and_season",
            strength="weak",
            hypothesis_title="罚罪",
        )
        duplicate = core.TmdbCandidate(
            tmdb_id=296146,
            title="罚罪2",
            year="2025",
            season=1,
            season_year="2025",
            season_episode_count=40,
            actors=("黄景瑜",),
            mode="exact_title",
            strength="exact",
            hypothesis_title="罚罪2",
        )
        decision = core.choose_match([
            core.score_candidate(self.source, duplicate),
            core.score_candidate(self.source, parent),
        ])
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.winner.candidate.tmdb_id, 208919)
        self.assertEqual(decision.winner.candidate.season, 2)

    def test_low_score_is_not_accepted(self) -> None:
        candidate = core.TmdbCandidate(
            tmdb_id=1,
            title="完全不同",
            year="2010",
            season=1,
        )
        decision = core.choose_match([core.score_candidate(self.source, candidate)])
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "low_score")

    def test_close_top_candidates_are_not_accepted(self) -> None:
        candidates = [
            core.TmdbCandidate(
                tmdb_id=tmdb_id,
                title="罚罪2",
                year="2025",
                season=1,
                actors=("黄景瑜", "王传君"),
                directors=("天毅",),
            )
            for tmdb_id in (3, 4)
        ]
        decision = core.choose_match([
            core.score_candidate(self.source, candidate)
            for candidate in candidates
        ])
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.status, "ambiguous")

    def test_malformed_year_does_not_abort_scoring(self) -> None:
        candidate = core.TmdbCandidate(
            tmdb_id=2,
            title="罚罪2",
            year="unknown",
            season=1,
        )
        source = {**self.source, "year": "2025年"}
        scored = core.score_candidate(source, candidate)
        self.assertGreaterEqual(scored.score, 35)


if __name__ == "__main__":
    unittest.main()
