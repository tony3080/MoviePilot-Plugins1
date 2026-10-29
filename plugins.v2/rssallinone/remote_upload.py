"""CD2 upload worker with bounded instant probes and persistent fallback policy."""

from __future__ import annotations

import hashlib
import queue
import threading
import time
import uuid
from pathlib import Path
from pathlib import PurePosixPath

from .cd2_wire import Client, MESSAGES as msg


RESPONSE_IDLE_TIMEOUT = 60


class UploadError(RuntimeError):
    pass


class UploadIdleTimeout(UploadError):
    pass


class CloudConflict(UploadError):
    pass


class NotInstant(UploadError):
    def __init__(self, message, sha1=""):
        super().__init__(message)
        self.sha1 = sha1


def describe_error(error, token=""):
    text = str(error).strip() or type(error).__name__
    return text.replace(token, "[REDACTED]") if token else text


def identity(path):
    item = Path(path).resolve(strict=True)
    stat = item.stat()
    if not item.is_file() or stat.st_size <= 0:
        raise UploadError("目标必须是非空文件")
    return {
        "path": str(item), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns, "device": stat.st_dev, "inode": stat.st_ino,
    }


def sha1_file(item, stop=None):
    digest = hashlib.sha1()
    with open(item["path"], "rb") as stream:
        while True:
            if stop is not None and stop.is_set():
                raise UploadError("上传任务已停止")
            data = stream.read(4 * 1024 * 1024)
            if not data:
                break
            digest.update(data)
    if identity(item["path"]) != item:
        raise UploadError("计算 SHA1 期间文件发生变化")
    return digest.hexdigest()


def verify_existing(client, destination, size, sha1, metadata, stop):
    target = PurePosixPath(destination)
    listing = client.GetSubFiles(
        msg["ListRequest"](path=str(target.parent), forceRefresh=True),
        metadata=metadata, timeout=30,
    )
    match = None
    try:
        # Consume every page so a later listing error cannot look like success.
        for page in listing:
            if stop.is_set():
                raise UploadError("上传任务已停止")
            for entry in page.subFiles:
                if entry.fullPathName != destination:
                    continue
                if match is not None:
                    raise CloudConflict("云端目标路径返回多条记录，需要人工核查")
                match = entry
    finally:
        if hasattr(listing, "cancel"):
            listing.cancel()
    if match is None:
        raise UploadError("CD2 跳过了上传，但刷新目录后未找到云端目标文件")
    if match.isDirectory or match.isLocal or match.fileType != 1:
        raise CloudConflict("云端目标不是预期的云端文件，需要人工核查")
    if match.size != size:
        raise CloudConflict(f"云端同路径文件大小不一致：本地={size}，云端={match.size}")
    cloud_sha1 = match.fileHashes.get(2, "").strip()
    if cloud_sha1 and cloud_sha1.lower() != sha1.lower():
        raise CloudConflict("云端同路径文件 SHA1 不一致，需要人工核查")
    return {
        "cloud_path": destination, "cloud_size": match.size,
        "cloud_sha1": cloud_sha1, "verification": "sha1" if cloud_sha1 else "size",
    }


def upload_once(config, item, stop=None, emit=None, on_hash=None,
                allow_full_upload=False, on_noninstant=None):
    import grpc

    log = emit or (lambda text: None)
    stop = stop or threading.Event()
    address, token = str(config.get("address") or "").strip(), str(config.get("token") or "").strip()
    if not address or not token or "://" in address:
        raise UploadError("CD2 gRPC 地址或令牌未配置")
    max_request = max(128 * 1024, min(16 * 1024 * 1024, int(config.get("max_request_bytes") or 4 * 1024 * 1024)))
    max_probe = max(max_request, min(64 * 1024 * 1024, int(config.get("max_probe_bytes") or 16 * 1024 * 1024)))
    probe_timeout = max(60, min(7200, int(config.get("attempt_timeout") or 1800)))
    full_timeout = max(60, min(604800, int(config.get("full_upload_timeout") or 86400)))
    full_upload = bool(allow_full_upload)
    deadline = time.monotonic() + (full_timeout if full_upload else probe_timeout)
    metadata = (("authorization", "Bearer " + token),)
    channel = grpc.insecure_channel(address)
    stream = None
    upload_id = ""
    finished = False
    sent = 0
    transferred = False
    expected = {
        key: item[key]
        for key in ("path", "size", "mtime_ns", "ctime_ns", "device", "inode")
        if key in item
    }
    events = queue.Queue(maxsize=256)
    done = threading.Event()
    receiver_started = threading.Event()
    receiver = None
    callback_started_at = None
    callback_events = 0
    ignored_events = 0
    valid_callback_seen = False
    try:
        client = Client(channel)
        info = client.GetSystemInfo(msg["Empty"](), metadata=metadata, timeout=15)
        if not info.IsLogin or not info.SystemReady:
            raise UploadError("CD2 尚未登录或未就绪")
        try:
            cache_sha1 = str(item.get("sha1") or "").strip()
            if identity(expected["path"]) != expected:
                raise UploadError("开始上传前媒体文件已变化")
            if len(cache_sha1) != 40 or any(char not in "0123456789abcdefABCDEF" for char in cache_sha1):
                log("开始计算本地 SHA1：文件=" + expected["path"])
                cache_sha1 = sha1_file(expected, stop)
                item["sha1"] = cache_sha1
                if on_hash is not None:
                    on_hash(cache_sha1)
                    log("SHA1 已计算并保存到数据库：" + cache_sha1)
                else:
                    log("已计算本地 SHA1：" + cache_sha1)
            else:
                log("复用已保存 SHA1，无需重新计算：" + cache_sha1)
        except FileNotFoundError as error:
            raise UploadError("媒体文件已不存在") from error
        if stop.is_set():
            raise UploadError("上传任务已停止")
        if time.monotonic() >= deadline:
            raise UploadError("上传尝试超时")
        destination = str(item["destination"])
        stream = client.RemoteUploadChannel(
            msg["ChannelRequest"](device_id="mp-cd2-media-" + uuid.uuid4().hex),
            metadata=metadata, timeout=max(probe_timeout, full_timeout) + 60,
        )
        log("CD2 回调通道调用已创建，等待接收线程开始读取")

        def enqueue(kind, event):
            while not done.is_set():
                try:
                    events.put((kind, event), timeout=0.2)
                    return
                except queue.Full:
                    continue

        def receive():
            nonlocal callback_started_at
            callback_started_at = time.monotonic()
            receiver_started.set()
            log("CD2 回调通道接收线程已开始读取")
            try:
                for event in stream:
                    if done.is_set():
                        break
                    enqueue("event", event)
            except Exception as error:
                log("CD2 回调通道异常结束：" + describe_error(error, token))
                enqueue("error", error)
            finally:
                log("CD2 回调通道接收线程已结束")
                enqueue("end", None)

        receiver = threading.Thread(target=receive, daemon=True, name="cd2-media-events")
        receiver.start()
        # Starting the receiver before StartRemoteUpload narrows the race where
        # CD2 emits the first event before the client is consuming the stream.
        # The event is diagnostic only; the gRPC call itself remains the source
        # of truth for channel readiness.
        if receiver_started.wait(timeout=5):
            log("CD2 回调通道已进入接收状态，开始创建上传会话")
        else:
            log("CD2 回调通道接收线程 5 秒内未确认启动，仍继续创建上传会话")
        started = client.StartRemoteUpload(
            msg["StartRequest"](
                file_path=destination, file_size=item["size"],
                known_hashes={2: cache_sha1}, client_can_calculate_hashes=True,
            ), metadata=metadata, timeout=30,
        )
        upload_id = started.upload_id
        if not upload_id:
            raise UploadError("CD2 没有返回 upload_id")
        log(
            f"CD2 上传会话开始：会话={upload_id}，目标={destination}，已提交 SHA1，"
            f"回调通道状态={'已启动' if receiver_started.is_set() else '未确认'}"
        )
        if full_upload:
            log("本次会话优先秒传，无法秒传时允许正常上传：" + destination)
        previous_status = None
        progress_at = time.monotonic()
        response_at = progress_at
        received_response = False
        while True:
            if stop.is_set():
                raise UploadError("上传任务已停止")
            now = time.monotonic()
            idle_remaining = RESPONSE_IDLE_TIMEOUT - (now - response_at)
            if idle_remaining <= 0:
                context = (
                    f"最后状态={previous_status}" if received_response
                    else "尚未收到本会话的有效响应"
                )
                message = (
                    f"CD2 连续 {RESPONSE_IDLE_TIMEOUT} 秒无有效响应："
                    f"会话={upload_id}，{context}"
                )
                log(message)
                raise UploadIdleTimeout(message)
            if now >= deadline:
                raise UploadError("上传尝试超时")
            try:
                kind, event = events.get(
                    timeout=min(0.5, idle_remaining, max(0.001, deadline - now))
                )
            except queue.Empty:
                continue
            if kind == "error":
                raise event
            if kind == "end":
                raise UploadError("CD2 回调通道提前结束")
            callback_events += 1
            if event.upload_id != upload_id:
                ignored_events += 1
                if ignored_events <= 5:
                    log(
                        f"CD2 收到其他会话回调：当前会话={upload_id}，"
                        f"回调会话={event.upload_id or '<空>'}"
                    )
                continue
            event_kind = event.WhichOneof("request")
            if not valid_callback_seen:
                elapsed = (
                    time.monotonic() - callback_started_at
                    if callback_started_at is not None else 0
                )
                log(
                    f"CD2 收到本会话首个回调：会话={upload_id}，"
                    f"类型={event_kind or '<空>'}，通道启动后={elapsed:.3f} 秒"
                )
                valid_callback_seen = True
            if event_kind == "hash_data":
                request = event.hash_data
                if request.hash_type != 2:
                    raise UploadError(f"CD2 请求了不支持的哈希类型：{request.hash_type}")
                client.RemoteHashProgress(
                    msg["HashProgress"](
                        upload_id=upload_id, bytes_hashed=item["size"],
                        total_bytes=item["size"], hash_type=2, hash_value=cache_sha1,
                    ),
                    metadata=metadata, timeout=20,
                )
            elif event_kind == "read_data":
                request = event.read_data
                length = int(request.length)
                if length <= 0 or int(request.offset) < 0 or int(request.offset) + length > item["size"]:
                    raise UploadError("CD2 请求的读取范围无效")
                if not full_upload and (length > max_request or sent + length > max_probe):
                    raise UploadError(
                        f"CD2 请求读取 {length} 字节，超过本次秒传探测上限；"
                        "尚未收到实际传输状态，不计入非秒传次数"
                    )
                offset = int(request.offset)
                remaining = length
                with open(expected["path"], "rb") as stream_file:
                    stream_file.seek(offset)
                    while remaining:
                        if stop.is_set():
                            raise UploadError("上传任务已停止")
                        if time.monotonic() >= deadline:
                            raise UploadError("上传尝试超时")
                        if identity(expected["path"]) != expected:
                            raise UploadError("发送文件数据前发现媒体文件已变化")
                        chunk_size = min(remaining, max_request, 1024 * 1024)
                        payload = stream_file.read(chunk_size)
                        if len(payload) != chunk_size or identity(expected["path"]) != expected:
                            raise UploadError("读取文件数据时媒体文件发生变化")
                        reply = client.RemoteReadData(
                            msg["ReadUpload"](
                                upload_id=upload_id, offset=offset, length=chunk_size,
                                lazy_read=request.lazy_read, data=payload,
                                is_last_chunk=remaining == chunk_size,
                            ),
                            metadata=metadata, timeout=20,
                        )
                        if not reply.success or reply.bytes_received != chunk_size:
                            detail = describe_error(reply.error_message, token) if reply.error_message else ""
                            raise UploadError("CD2 未确认接收完整文件数据：" + detail)
                        sent += chunk_size
                        offset += chunk_size
                        remaining -= chunk_size
                        if full_upload and time.monotonic() - progress_at >= 10:
                            progress_at = time.monotonic()
                            log(f"正常上传进度：目标={destination}，本会话累计确认发送={sent} 字节")
                if not full_upload:
                    log(f"已发送校验片段：偏移={request.offset}，长度={length}")
            elif event_kind == "status_changed":
                status = event.status_changed
                if status.status != previous_status:
                    previous_status = status.status
                    detail = describe_error(status.error_message, token) if status.error_message else ""
                    log(f"CD2 会话状态：会话={upload_id}，状态={status.status}，说明={detail}")
                if status.status == 5:
                    if identity(expected["path"]) != expected:
                        raise UploadError("CD2 返回完成时媒体文件已变化")
                    finished = True
                    return {
                        "status": "completed", "sent_bytes": sent, "sha1": cache_sha1,
                        "result": "uploaded" if transferred else "instant",
                    }
                if status.status == 6:
                    finished = True
                    verification = verify_existing(
                        client, destination, item["size"], cache_sha1, metadata, stop,
                    )
                    if identity(expected["path"]) != expected:
                        raise UploadError("核对云端文件时本地媒体文件已变化")
                    basis = "路径、大小和 SHA1" if verification["verification"] == "sha1" else "路径和大小（云端未提供 SHA1）"
                    log(f"云端目标已存在，核对通过：目标={destination}，依据={basis}")
                    return {
                        "status": "completed", "sent_bytes": sent, "sha1": cache_sha1,
                        "result": "already_exists", **verification,
                    }
                if status.status == 3:
                    if not full_upload:
                        if on_noninstant is None or not on_noninstant():
                            raise NotInstant("CD2 已进入真实传输，本次入库回退", cache_sha1)
                        full_upload = True
                        deadline = time.monotonic() + full_timeout
                        log("累计 3 次非秒传，当前会话转为正常上传：" + destination)
                    elif not transferred:
                        log("CD2 未能秒传，当前会话继续正常上传：" + destination)
                    transferred = True
                if status.status in (2, 8, 9, 10):
                    raise UploadError(
                        f"CD2 上传失败：状态={status.status}"
                        + (f"，原因={describe_error(status.error_message, token)}" if status.error_message else "")
                    )
            else:
                continue
            # Start the next wait after local reads and request replies have finished.
            received_response = True
            response_at = time.monotonic()
    finally:
        done.set()
        if ignored_events > 5:
            log(f"CD2 其他会话回调已忽略：数量={ignored_events}，当前会话={upload_id or '<未创建>'}")
        if upload_id and not finished:
            try:
                client.RemoteUploadControl(
                    msg["ControlRequest"](upload_id=upload_id, cancel={}),
                    metadata=metadata, timeout=15,
                )
                log(f"已发送 CD2 会话取消请求：会话={upload_id}")
            except Exception as error:
                log(f"取消 CD2 会话失败：会话={upload_id}，原因={describe_error(error, token)}")
        if stream is not None:
            try:
                stream.cancel()
            except Exception as error:
                log("关闭 CD2 回调通道失败：" + describe_error(error, token))
        try:
            channel.close()
        except Exception as error:
            log("关闭 CD2 连接失败：" + describe_error(error, token))
        if receiver is not None:
            receiver.join(timeout=1)
