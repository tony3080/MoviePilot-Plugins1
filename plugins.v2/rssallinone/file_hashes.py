"""Content hashes shared by original files, renamed paths and hardlinks."""

from __future__ import annotations

import hashlib
import os
import queue
import threading

from .database import file_identity


class FileHashCache:
    _read_lock = threading.Lock()

    def __init__(self, store, stop_event, logger):
        self.store = store
        self.stop = stop_event
        self.logger = logger

    @staticmethod
    def identity(path):
        return file_identity(path)

    def ensure(self, path):
        with self._read_lock:
            source, stat, key = self.identity(path)
            value = self.store.get_file_sha1(key)
            if value:
                return value
            self.logger.info(f"RSS一条龙：开始计算文件 SHA1：{source}")
            digest = hashlib.sha1()
            with source.open("rb") as stream:
                opened = stream.fileno()
                initial = os.fstat(opened)
                if (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns) != (
                    stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
                ):
                    raise RuntimeError("计算 SHA1 前文件发生变化")
                while True:
                    if self.stop.is_set():
                        raise RuntimeError("SHA1 计算已停止")
                    data = stream.read(4 * 1024 * 1024)
                    if not data:
                        break
                    digest.update(data)
                after = os.fstat(opened)
            if self.identity(source)[2] != key or (
                after.st_size, after.st_mtime_ns
            ) != (stat.st_size, stat.st_mtime_ns):
                raise RuntimeError("计算 SHA1 期间文件发生变化")
            value = digest.hexdigest()
            self.store.save_file_sha1(key, value, str(source), stat.st_size)
            self.logger.info(f"RSS一条龙：文件 SHA1 已保存：{source}，SHA1={value}")
            return value

    def prepare_media(self, media_id):
        item = self.store.get_media_item(media_id)
        # Old queues may contain file-manager cards from before completion-only prehashing.
        if (
            not item
            or item.get("state") in {"existing", "imported", "importing"}
            or item.get("downloader_id") == "FILE"
            or ((item.get("details") or {}).get("source_identity") or {}).get("kind") == "local_file"
        ):
            self.store.finish_hash_preparation(media_id)
            return
        paths = self.store.initial_hash_paths(media_id)
        for path in dict.fromkeys(value for value in paths if value):
            current = self.store.get_media_item(media_id)
            if self.stop.is_set():
                return
            if not current or current.get("state") in {"existing", "imported", "importing"}:
                break
            try:
                self.ensure(path)
            except Exception as error:
                if self.stop.is_set():
                    return
                self.logger.warning(f"RSS一条龙：文件 SHA1 预计算失败，入库时会重试：{path}：{error}")
        self.store.finish_hash_preparation(media_id)


class FileHashWorker:
    """One disk reader, independent of RSS, recognition and downloader callbacks."""

    def __init__(self, cache):
        self.cache = cache
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.queued = set()
        self.thread = None

    def submit(self, media_id):
        if not media_id or self.cache.stop.is_set():
            return
        with self.lock:
            if media_id not in self.queued:
                self.queued.add(media_id)
                self.queue.put(media_id)
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name="RssAllInOneSha1", daemon=True)
                self.thread.start()

    def run(self):
        while not self.cache.stop.is_set():
            with self.lock:
                try:
                    media_id = self.queue.get_nowait()
                except queue.Empty:
                    self.thread = None
                    return
                self.queued.discard(media_id)
            try:
                self.cache.prepare_media(media_id)
            except Exception as error:
                if not self.cache.stop.is_set():
                    self.cache.logger.warning(f"RSS一条龙：文件 SHA1 预计算失败，入库时会重试：{error}")
        with self.lock:
            self.thread = None
