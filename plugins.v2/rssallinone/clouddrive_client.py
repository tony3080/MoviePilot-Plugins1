"""CloudDrive2 gRPC upload task client."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


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
        try:
            with grpc.insecure_channel(self.address) as channel:
                response = pb2_grpc.CloudDriveFileSrvStub(channel).GetUploadFileList(
                    pb2.GetUploadFileListRequest(
                        getAll=True,
                        itemsPerPage=1000,
                        pageNumber=1,
                    ),
                    metadata=self.metadata,
                    timeout=self.timeout,
                )
        except Exception as error:
            raise CloudDriveError(f"读取 CloudDrive2 上传列表失败：{error}") from error
        items = []
        for row in response.uploadFiles:
            try:
                status_name = pb2.UploadFileInfo.Status.Name(int(row.statusEnum))
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
        return items

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
