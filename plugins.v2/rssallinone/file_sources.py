"""Backfill durable file origins without hashing or blocking plugin APIs."""

import threading


class FileSourceIndexer:
    def __init__(self, store, logger):
        self.store = store
        self.logger = logger
        self.stop = threading.Event()
        self.thread = threading.Thread(
            target=self.run, name="RssAllInOneFileSources", daemon=True,
        )

    def run(self):
        try:
            count = self.store.backfill_file_sources(self.stop)
            if count:
                self.logger.info(f"RSS一条龙：已有卡片文件来源关联完成，检查={count}")
        except Exception:
            self.logger.error("RSS一条龙：文件来源关联未完成，下次启动继续", exc_info=True)
