"""MoviePilot V2 Douban subscription plugin."""

from typing import Any, Dict, List, Tuple

from app.plugins import _PluginBase


class DoubanSubscribe(_PluginBase):
    """Match Douban entries to TMDB titles and seasons for subscriptions."""

    plugin_name = "豆瓣订阅助手"
    plugin_desc = "匹配豆瓣条目与 TMDB 作品及季度，并创建准确的 MoviePilot 订阅。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/"
        "MoviePilot-Plugins/main/icons/douban.png"
    )
    plugin_version = "0.1.0"
    plugin_author = "tony3080"
    author_url = "https://github.com/tony3080"
    plugin_config_prefix = "doubansubscribe_"
    plugin_order = 50
    auth_level = 2

    _enabled = False

    def init_plugin(self, config: dict = None) -> None:
        """Load the plugin configuration."""
        config = config or {}
        self._enabled = bool(config.get("enabled"))

    def get_state(self) -> bool:
        """Return whether the plugin is enabled."""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """Return remote commands exposed by the plugin."""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """Return API routes exposed by the plugin."""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Build the initial MoviePilot configuration form."""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ], {"enabled": False}

    def get_page(self) -> List[dict]:
        """Build the plugin details page."""
        return [
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": "豆瓣与 TMDB 匹配功能正在开发中。",
                },
            }
        ]

    def stop_service(self) -> None:
        """Release resources owned by the plugin."""
        pass
