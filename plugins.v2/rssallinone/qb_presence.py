"""Check qB task presence without refreshing or recognizing plugin cards."""

from typing import Any, Dict

from .database import SQLiteStore


class QbPresenceCheckService:
    def __init__(self, store: SQLiteStore, gateway: Any):
        self.store = store
        self.gateway = gateway

    def check(self, *, downloader_id: str = "", keyword: str = "") -> Dict[str, Any]:
        snapshots = self.store.list_pending_torrent_snapshots(
            downloader_id=downloader_id, keyword=keyword
        )
        result = {
            "total": len(snapshots), "existing": 0, "deleted": 0,
            "skipped": 0, "failed": 0, "errors": [],
        }
        nodes = {}
        for snapshot in snapshots:
            nodes.setdefault(snapshot["downloader_id"], []).append(snapshot)
        for downloader, cards in nodes.items():
            try:
                if not downloader or any(not card["info_hash"].strip() for card in cards):
                    raise RuntimeError("卡片缺少 qB 节点或种子 Hash")
                torrents = self.gateway.list_torrents(downloader)
                if not isinstance(torrents, (list, tuple)):
                    raise RuntimeError("qB 未返回有效的任务列表")
                hashes = set()
                # Validate the whole response before treating any card as absent.
                for torrent in torrents:
                    raw = self.gateway.torrent_dict(torrent)
                    info_hash = raw.get("hash")
                    if not isinstance(info_hash, str) or not info_hash.strip():
                        raise RuntimeError("qB 任务列表包含缺少 Hash 的记录，本节点不清理")
                    hashes.add(info_hash.strip().lower())
            except Exception as error:
                result["failed"] += len(cards)
                result["errors"].append({
                    "downloader_id": downloader, "message": str(error),
                })
                continue
            for snapshot in cards:
                if snapshot["info_hash"].strip().lower() in hashes:
                    result["existing"] += 1
                else:
                    try:
                        if self.store.delete_missing_pending_snapshot(snapshot):
                            result["deleted"] += 1
                        else:
                            result["skipped"] += 1
                    except Exception as error:
                        result["failed"] += 1
                        result["errors"].append({
                            "downloader_id": downloader,
                            "info_hash": snapshot["info_hash"],
                            "message": str(error),
                        })
        result["success"] = result["failed"] == 0
        result["partial"] = 0 < result["failed"] < result["total"]
        result["message"] = (
            f"核对 {result['total']} 项，仍存在 {result['existing']} 项，"
            f"已清理 {result['deleted']} 项，查询或清理失败 {result['failed']} 项"
        )
        if result["skipped"]:
            result["message"] += f"，卡片已变化或移除，跳过 {result['skipped']} 项"
        return result
