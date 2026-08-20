"""Rainbow Island HR list parsing tests."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v2" / "rssallinone"
PACKAGE = "rssallinone_chd_hr_tests"


def load_package_module(name: str):
    package = sys.modules.get(PACKAGE)
    if package is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PACKAGE] = package
    module_name = f"{PACKAGE}.{name}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


rss_site_labels = load_package_module("rss_site_labels")


class ChdHrParseTest(unittest.TestCase):
    def test_parse_ignores_user_id_and_login_pages(self) -> None:
        ids = rss_site_labels.parse_chd_hr_torrent_ids(
            """
            <title>CHDBits :: Hit And Runs - Powered by NexusPHP</title>
            <a href="userdetails.php?id=1794">me</a>
            <a href="details.php?id=571440&amp;hit=1">one</a>
            <a href="details.php?id=571331&hit=1">two</a>
            """
        )
        self.assertEqual(ids, ["571440", "571331"])
        with self.assertRaises(rss_site_labels.ChdHrError):
            rss_site_labels.parse_chd_hr_torrent_ids(
                "<title>登录</title><a href=\"takelogin.php\">login</a>"
            )

    def test_list_url_uses_cookie_uid_or_page_uid(self) -> None:
        access = types.SimpleNamespace(cookie="c_secure_uid=MTc5NA==")
        self.assertEqual(
            rss_site_labels.chd_hr_list_url(access),
            "https://ptchdbits.co/hnr.php?id=1794",
        )
        self.assertEqual(
            rss_site_labels.chd_hr_list_url(
                types.SimpleNamespace(cookie=""),
                '<a href="userdetails.php?id=1794">me</a>',
            ),
            "https://ptchdbits.co/hnr.php?id=1794",
        )
        self.assertEqual(
            rss_site_labels.chd_hr_list_url(
                types.SimpleNamespace(cookie="c_secure_uid=MTc5NA%3D%3D")
            ),
            "https://ptchdbits.co/hnr.php?id=1794",
        )


if __name__ == "__main__":
    unittest.main()
