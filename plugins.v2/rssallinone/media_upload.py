"""Upload persisted hardlink mappings without relying on CD2 backup jobs."""

import threading
import time
from pathlib import Path
from pathlib import PurePosixPath

from .database import utc_now
from .file_hashes import FileHashCache
from .remote_upload import identity, upload_once


class UploadPacing:
    """Share the previous finished session across one plugin's upload services."""

    def __init__(self):
        self.lock = threading.Lock()
        self.finished_at = None
        self.media_id = ""


class MediaUploadService:
    def __init__(self, store, cd2, roots, cloud_root, stop_event, logger, timeout=1800,
                 pacing=None):
        self.store = store
        self.cd2 = cd2
        self.roots = list(roots)
        self.cloud_root = cloud_root
        self.stop = stop_event
        self.logger = logger
        self.timeout = timeout
        self.cache = FileHashCache(store, stop_event, logger)
        self.pacing = pacing if pacing is not None else UploadPacing()
        self._resolved_root = ""

    def _wait_for_upload(self, media_id):
        if self.pacing.finished_at is not None:
            interval = 3 if self.pacing.media_id == media_id else 5
            remaining = interval - (time.monotonic() - self.pacing.finished_at)
            if remaining > 0:
                self.logger.info(
                    f"RSS一条龙：上传间隔等待 {remaining:.1f} 秒，"
                    f"{'同一卡片' if interval == 3 else '切换卡片'}"
                )
                if self.stop.wait(remaining):
                    raise RuntimeError("CD2 入库已停止")
        if self.stop.is_set():
            raise RuntimeError("CD2 入库已停止")

    @property
    def ready(self):
        return self.cd2.ready and bool(self.roots) and bool(self.cloud_root)

    def destination(self, path):
        local = Path(path).expanduser().resolve(strict=False)
        matches = []
        for value in self.roots:
            root = Path(value).expanduser().resolve(strict=False)
            try:
                relative = local.relative_to(root)
            except ValueError:
                continue
            matches.append((len(root.parts), relative))
        if not matches:
            raise RuntimeError(f"硬链接路径未命中已配置根目录：{local}")
        if not self._resolved_root:
            self._resolved_root = self.cd2.resolve_destination_root(self.cloud_root)
        root = PurePosixPath(self._resolved_root)
        if not root.is_absolute() or str(root) == "/":
            raise RuntimeError("CD2 云端目标根目录无效")
        return str(root / PurePosixPath(*max(matches, key=lambda pair: pair[0])[1].parts))

    def __call__(self, media_id, mappings, *, allow_full_upload=False):
        if not self.ready:
            raise RuntimeError("CD2 连接或目录配置不完整")
        results = []
        for mapping in mappings:
            if self.stop.is_set():
                raise RuntimeError("CD2 入库已停止")
            path = str(mapping.get("local_hardlink_path") or "")
            destination = self.destination(path)
            # A persisted SHA1 follows the inode across hardlinks and renames.
            fingerprint = identity(path)
            sha1 = self.cache.ensure(path)
            if identity(path) != fingerprint:
                raise RuntimeError("取得 SHA1 后文件发生变化，停止本次入库")
            item = {**fingerprint, "sha1": sha1, "destination": destination}
            with self.pacing.lock:
                self._wait_for_upload(media_id)
                try:
                    result = upload_once(
                        {"address": self.cd2.address, "token": self.cd2.token,
                         "attempt_timeout": self.timeout},
                        item, self.stop,
                        emit=lambda text: self.logger.info("RSS一条龙：" + text),
                        allow_full_upload=allow_full_upload,
                    )
                finally:
                    # upload_once returns/raises only after closing its session.
                    self.pacing.finished_at = time.monotonic()
                    self.pacing.media_id = media_id
            results.append(result)
            self.store.save_mapping_upload_result(
                media_id, int(mapping.get("file_index") or 0),
                {"destination": destination, **result, "completed_at": utc_now()},
            )
        return results
