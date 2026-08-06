"""Unit tests for the Checkin response parsers."""

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "plugins.v2" / "checkin" / "core.py"
SPEC = importlib.util.spec_from_file_location("checkin_core", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


class CheckinCoreTest(unittest.TestCase):
    def test_cookie_normalization_accepts_multiline_copy(self) -> None:
        self.assertEqual(
            CORE.normalize_cookie("a=1; b=2\nc=3; empty="),
            "a=1; b=2; c=3",
        )

    def test_smzdm_success_jsonp_is_parsed(self) -> None:
        result = CORE.parse_smzdm_response(
            'callback({"error_code":0,"error_msg":"签到成功",'
            '"data":{"checkin":{"daily_num":"21","cpoints":"5"}}})'
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["days"], "21")
        self.assertEqual(result["points"], "5")

    def test_smzdm_already_done_uses_message_not_broad_error_codes(self) -> None:
        result = CORE.parse_smzdm_response(
            '{"error_code":1,"error_msg":{"public":"今天已经签到"}}'
        )
        self.assertEqual(result["status"], "already")
        failed = CORE.parse_smzdm_response(
            '{"error_code":-1,"error_msg":"登录失效"}'
        )
        self.assertEqual(failed["status"], "failed")

    def test_chiphell_requires_a_real_login_marker(self) -> None:
        failed = CORE.parse_chiphell_page("<html><body>用户组</body></html>")
        self.assertEqual(failed["status"], "failed")
        result = CORE.parse_chiphell_page(
            '<strong class="vwmy"><a>tester</a></strong>'
            '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
            '<span>积分: 1234</span>'
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["username"], "tester")
        self.assertEqual(result["points"], "1234")

    def test_history_pruning_honors_age_and_limit(self) -> None:
        rows = [
            {"date": "2026-07-01 00:00:00", "status": "failed"},
            {"date": "2026-08-05 00:00:00", "status": "success"},
            {"date": "invalid", "status": "failed"},
        ]
        result = CORE.prune_history(
            rows,
            keep_days=30,
            now=datetime(2026, 8, 6, 12, 0, 0),
            limit=2,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
