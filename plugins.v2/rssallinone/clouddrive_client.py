"""CloudDrive2 gRPC upload task client."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote


class CloudDriveError(RuntimeError):
    """Raised when CloudDrive2 cannot be queried or controlled."""


class CloudDriveClient:
    def __init__(self, address: str, token: str, *, timeout: int = 20):
        self.address = str(address or "").strip()
        self.token = str(token or "").strip()
        self.timeout = max(5, int(timeout or 20))

    @property
    def ready(self) -> bool:
        return bool(self.address and self.token)

    @property
    def metadata(self):
        return (("authorization", f"Bearer {self.token}"),)

    def _runtime(self):
        if not self.ready:
            raise CloudDriveError("CloudDrive2 gRPC 地址或令牌未配置")
        try:
            import grpc
            from .generated import clouddrive_pb2, clouddrive_pb2_grpc
        except ImportError as error:
            raise CloudDriveError("CloudDrive2 gRPC 运行依赖不可用") from error
        return grpc, clouddrive_pb2, clouddrive_pb2_grpc

    def list_uploads(self) -> List[Dict[str, Any]]:
        grpc, pb2, pb2_grpc = self._runtime()
        items = []
        page = 1
        page_size = 500
        try:
            with grpc.insecure_channel(self.address) as channel:
                stub = pb2_grpc.CloudDriveFileSrvStub(channel)
                while page <= 100:
                    response = stub.GetUploadFileList(
                        pb2.GetUploadFileListRequest(
                            getAll=True,
                            itemsPerPage=page_size,
                            pageNumber=page,
                        ),
                        metadata=self.metadata,
                        timeout=self.timeout,
                    )
                    rows = list(response.uploadFiles)
                    for row in rows:
                        try:
                            status_name = pb2.UploadFileInfo.Status.Name(
                                int(row.statusEnum)
                            )
                        except (TypeError, ValueError):
                            status_name = str(row.status or row.statusEnum or "")
                        items.append({
                            "key": str(row.key or ""),
                            "dest_path": str(row.destPath or ""),
                            "size": int(row.size or 0),
                            "transferred_bytes": int(row.transferedBytes or 0),
                            "status": status_name,
                            "status_enum": int(row.statusEnum),
                            "error_message": str(row.errorMessage or ""),
                            "operator_type": int(row.operatorType),
                        })
                    total = int(
                        getattr(response, "totalCountFiltered", 0)
                        or getattr(response, "totalCount", 0)
                        or 0
                    )
                    if (
                        not rows
                        or (total > 0 and len(items) >= total)
                        or len(rows) < page_size
                    ):
                        break
                    page += 1
        except Exception as error:
            raise CloudDriveError(f"读取 CloudDrive2 上传列表失败：{error}") from error
        return items

    def find_file(
        self, path: object, *, force_refresh: bool = False
    ) -> Dict[str, Any] | None:
        """Return exact cloud-file metadata without treating a missing path as an error."""
        return self.find_files([path], force_refresh=force_refresh).get(
            _cd2_path_key(path)
        )

    def find_files(
        self, paths: Iterable[object], *, force_refresh: bool = False
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        requested = {
            _cd2_path_key(value): _normalized_cd2_path(value)
            for value in paths or []
            if _normalized_cd2_path(value) not in {"", ".", "/"}
        }
        results: Dict[str, Optional[Dict[str, Any]]] = {
            key: None for key in requested
        }
        if not requested:
            return results
        grpc, pb2, pb2_grpc = self._runtime()
        try:
            with grpc.insecure_channel(self.address) as channel:
                stub = pb2_grpc.CloudDriveFileSrvStub(channel)
                if force_refresh:
                    grouped: Dict[str, Dict[str, List[str]]] = {}
                    for key, requested_path in requested.items():
                        parent = str(PurePosixPath(requested_path).parent)
                        name = PurePosixPath(requested_path).name.casefold()
                        grouped.setdefault(parent, {}).setdefault(name, []).append(key)
                    for parent, names in grouped.items():
                        try:
                            replies = stub.GetSubFiles(
                                pb2.ListSubFileRequest(
                                    path=parent,
                                    forceRefresh=True,
                                    checkExpires=True,
                                ),
                                metadata=self.metadata,
                                timeout=self.timeout,
                            )
                            for reply in replies:
                                for row in reply.subFiles:
                                    matched = names.get(
                                        str(row.name or "").casefold()
                                    )
                                    for key in matched or []:
                                        results[key] = _cloud_file_info(
                                            row, requested[key]
                                        )
                        except Exception as error:
                            if _is_not_found(grpc, error):
                                continue
                            raise
                    return results
                for key, requested_path in requested.items():
                    parent = str(PurePosixPath(requested_path).parent)
                    name = PurePosixPath(requested_path).name
                    try:
                        row = stub.FindFileByPath(
                            pb2.FindFileByPathRequest(parentPath=parent, path=name),
                            metadata=self.metadata,
                            timeout=self.timeout,
                        )
                    except Exception as error:
                        if _is_not_found(grpc, error):
                            continue
                        raise
                    if not str(row.name or "").strip() and not str(
                        row.fullPathName or ""
                    ).strip():
                        continue
                    results[key] = _cloud_file_info(row, requested_path)
                return results
        except Exception as error:
            raise CloudDriveError(f"读取 CloudDrive2 云端文件失败：{error}") from error

    def pause(self, keys: Iterable[object]) -> None:
        self._control("pause", keys)

    def cancel(self, keys: Iterable[object]) -> None:
        self._control("cancel", keys)

    def _control(self, action: str, keys: Iterable[object]) -> None:
        normalized = [str(value or "").strip() for value in keys or []]
        normalized = list(dict.fromkeys(value for value in normalized if value))
        if not normalized:
            return
        grpc, pb2, pb2_grpc = self._runtime()
        try:
            with grpc.insecure_channel(self.address) as channel:
                stub = pb2_grpc.CloudDriveFileSrvStub(channel)
                request = pb2.MultpleUploadFileKeyRequest(keys=normalized)
                method = stub.PauseUploadFiles if action == "pause" else stub.CancelUploadFiles
                method(request, metadata=self.metadata, timeout=self.timeout)
        except Exception as error:
            verb = "暂停" if action == "pause" else "取消"
            raise CloudDriveError(f"{verb} CloudDrive2 上传任务失败：{error}") from error


def _normalized_cd2_path(value: object) -> str:
    text = unquote(str(value or "").strip()).replace("\\", "/")
    if not text:
        return ""
    normalized = str(PurePosixPath(text))
    if text.startswith("/") and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _cd2_path_key(value: object) -> str:
    return _normalized_cd2_path(value).casefold()


def _is_not_found(grpc: Any, error: Exception) -> bool:
    code = getattr(error, "code", lambda: None)()
    return code == getattr(getattr(grpc, "StatusCode", object()), "NOT_FOUND", None)


def _cloud_file_info(row: Any, requested_path: str) -> Dict[str, Any]:
    full_path = _normalized_cd2_path(getattr(row, "fullPathName", ""))
    return {
        "id": str(getattr(row, "id", "") or ""),
        "name": str(getattr(row, "name", "") or ""),
        "full_path": full_path or requested_path,
        "size": int(getattr(row, "size", 0) or 0),
        "is_directory": bool(getattr(row, "isDirectory", False)),
        "create_time": _timestamp_text(getattr(row, "createTime", None)),
        "write_time": _timestamp_text(getattr(row, "writeTime", None)),
    }


def _timestamp_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        parsed = value.ToDatetime(tzinfo=timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError):
        seconds = int(getattr(value, "seconds", 0) or 0)
        if not seconds:
            return ""
        parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
