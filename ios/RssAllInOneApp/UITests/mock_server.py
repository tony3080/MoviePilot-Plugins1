"""Local API fixture for simulator UI tests. Never connects to a real NAS."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


TASK = {
    "id": "task-1", "name": "测试 RSS 任务", "enabled": True, "position": 0,
    "config": {
        "task_type": "rss", "rss_url": "https://pt.example/rss",
        "rss_cron": "19", "qb_downloader": "测试 qB", "qb_category": "REMUX",
        "site_id": "site-1", "recognize_cn": True, "recognize_fx": True,
    },
}
MEDIA = {
    "id": "media-1", "title": "测试电影", "media_type": "movie", "tmdb_id": 42,
    "state": "identified", "category": "外语电影",
    "source_name": "Test.Movie.2026.1080p.mkv",
    "source_path": "/media/Test.Movie.2026.1080p.mkv",
    "comment_url": "https://pt.example/details.php?id=123",
    "details": {
        "site_labels": {"mandarin": True, "effects": False},
        "file_mappings": [{"source_path": "/media/Test.Movie.2026.1080p.mkv",
                           "sha1": "a" * 40, "file_size": 1073741824}],
    },
}
TORRENT = {
    "downloader_id": "测试 qB", "info_hash": "b" * 40, "name": "测试下载任务",
    "recognition_state": "identified", "inventory_state": "missing", "progress": 0.52,
    "media_type": "movie", "tmdb_id": 42, "category": "REMUX",
    "details": {"site_labels": {"mandarin": True, "effects": True}},
}
CONFIG = {
    "enabled": True, "rss_enabled": True, "inventory_root": "/media/library",
    "pending_import_cron": "*/10 * * * *", "source_routes": [],
    "database_filename": "rssallinone.db", "cd2_grpc_addr": "cd2:19798",
    "cd2_token": "fixture-secret", "cd2_dest_root": "/115/影视库",
}
BACKGROUND = {
    "id": "background-1", "task_type": "rss_run", "task_name": "测试 RSS 任务",
    "state": "succeeded", "total": 1, "processed": 1, "updated_at": "2026-10-27T03:00:00Z",
}


def page(items, query):
    offset = int(query.get("offset", ["0"])[0])
    limit = int(query.get("limit", ["50"])[0])
    return {"success": True, "items": items[offset:offset + limit], "total": len(items)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Never log auth headers or request bodies.
        print(fmt % args, flush=True)

    def reply(self, value, status=200):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path.removeprefix("/api/v1/plugin/RssAllInOne").strip("/")
        if path == "":
            return self.reply(CONFIG)
        if path == "overview":
            return self.reply({
                "success": True, "plugin": {"version": "1.1.9", "enabled": True, "rss_enabled": True},
                "counts": {"media": 1, "torrents": 1, "rss_tasks": 1},
                "qb_task": None, "manual_task": None, "rss_tasks": [],
                "pending_import": {"running": False, "pending": 1},
            })
        if path == "media":
            state = query.get("state", [""])[0]
            return self.reply(page([MEDIA] if not state or state == MEDIA["state"] else [], query))
        if path == "torrents":
            return self.reply(page([TORRENT], query))
        if path == "rss/tasks":
            return self.reply(page([TASK], query))
        if path == "qb/downloaders":
            return self.reply(page([{"name": "测试 qB", "ready": True, "categories": ["REMUX"]}], query))
        if path == "sites":
            return self.reply(page([{"id": "site-1", "name": "测试站点", "domain": "https://pt.example",
                                     "enabled": True, "auth_mode": "Cookie", "ready": True}], query))
        if path == "categories":
            return self.reply({"success": True, "items": ["外语电影", "国产剧"]})
        if path == "files/browse":
            directory = query.get("path", ["/"])[0]
            entry = ({"name": "媒体目录", "type": "dir", "path": "/media"} if directory == "/" else
                     {"name": "测试文件.mkv", "type": "file", "path": "/media/测试文件.mkv"})
            return self.reply(page([entry], query))
        if path == "import/status":
            return self.reply({"success": True, "running": False, "pending": 1, "batch": None})
        if path == "tasks":
            return self.reply(page([], query))
        if path.startswith("tasks/"):
            return self.reply({"success": True, "task": BACKGROUND})
        if path == "rss/history":
            return self.reply(page([{"id": "history-1", "title": "测试电影", "status": "added",
                                     "updated_at": "2026-10-27T03:00:00Z"}], query))
        if path in {"layout", "health", "emby/scheduledtasks/callbacks"}:
            return self.reply({"success": True, "items": []})
        self.reply({"success": False, "message": "未提供的测试接口: " + path}, 404)

    def do_POST(self):
        count = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(count) or b"{}")
        path = urlsplit(self.path).path.removeprefix("/api/v1/plugin/RssAllInOne/").strip("/")
        if path == "qb/item/identify":
            if payload.get("media_id") != "media-1" or payload.get("tmdb_id") != 42:
                return self.reply({"success": False, "message": "识别参数错误"}, 400)
            if not payload.get("manual_labels", {}).get("effects"):
                return self.reply({"success": False, "message": "特效开关未传递"}, 400)
            MEDIA["details"]["site_labels"] = payload["manual_labels"]
            return self.reply({"success": True, "message": "识别已更新", "item": MEDIA})
        if path == "qb/check-presence":
            return self.reply({"success": True, "message": "核对完成：保留 1 项"})
        if path == "rss/test":
            if payload.get("task", {}).get("id") != "task-1":
                return self.reply({"success": False, "message": "缺少完整任务配置"}, 400)
            return self.reply({"success": True, "message": "读取 1 条，可处理 1 条",
                               "result": {"counts": {"total": 1, "ready": 1},
                                          "items": [{"title": "测试电影", "status": "ready"}]}})
        if path.startswith("external/"):
            return self.reply({"success": True, "enabled": False})
        self.reply({"success": False, "message": "未授权的测试写操作: " + path}, 400)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8767), Handler).serve_forever()
