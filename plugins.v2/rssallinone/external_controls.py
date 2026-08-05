"""Clients for the Emby catch-up switch and the external scan controller."""

from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ExternalControlError(RuntimeError):
    """Raised when an external switch cannot be read, changed, or verified."""


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是", "开启"}
    return bool(value)


class JsonHttpClient:
    """Small dependency-free HTTP helper with explicit status handling."""

    def __init__(self, timeout: int = 20):
        self.timeout = max(5, int(timeout or 20))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Any = None,
        form_body: Optional[Dict[str, Any]] = None,
        accepted: Iterable[int] = (200,),
    ) -> Tuple[int, Any]:
        request_headers = dict(headers or {})
        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif form_body is not None:
            data = urlencode(form_body).encode("utf-8")
            request_headers.setdefault(
                "Content-Type", "application/x-www-form-urlencoded"
            )
        request = Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200) or 0)
                raw = response.read()
        except HTTPError as error:
            raw = error.read()
            status = int(error.code or 0)
        except (URLError, OSError) as error:
            raise ExternalControlError(f"外部请求失败：{error}") from error
        if status not in set(int(value) for value in accepted):
            message = raw.decode("utf-8", errors="replace")[:500]
            raise ExternalControlError(f"外部请求返回 HTTP {status}：{message}")
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, raw.decode("utf-8", errors="replace")


class CatchupSwitchClient:
    """Read and update Emby's plugin-page CatchupMode value."""

    def __init__(
        self,
        base_url: str,
        page_id: str,
        token: str,
        *,
        http: Optional[JsonHttpClient] = None,
    ):
        self.base_url = str(base_url or "").rstrip("/")
        self.page_id = str(page_id or "").strip()
        self.token = str(token or "").strip()
        self.http = http or JsonHttpClient()

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.page_id and self.token)

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Emby-Token": self.token,
            "X-Emby-Client": "MediaFlow",
            "X-Emby-Device-Id": "mediaflow-pro",
            "X-Emby-Device-Name": "MediaFlow",
            "X-Emby-Version": "1.0.0",
        }

    def read(self) -> Dict[str, Any]:
        if not self.ready:
            raise ExternalControlError("追更开关配置不完整")
        query = urlencode({
            "PageId": self.page_id,
            "ClientLocale": "zh-cn",
            "X-Emby-Token": self.token,
        })
        _status, payload = self.http.request(
            "GET",
            f"{self.base_url}/emby/UI/View?{query}",
            headers=self._headers(),
        )
        if not isinstance(payload, dict):
            raise ExternalControlError("追更开关返回格式无效")
        container = payload.get("EditObjectContainer") or {}
        object_value = container.get("Object") or {}
        options = object_value.get("GeneralOptions") or {}
        if "CatchupMode" not in options:
            raise ExternalControlError("追更配置中缺少 CatchupMode")
        return {
            "enabled": _bool_value(options.get("CatchupMode")),
            "object": copy.deepcopy(object_value),
            "page_id": str(payload.get("PageId") or self.page_id),
            "plugin_id": payload.get("PluginId"),
        }

    def set_enabled(self, enabled: bool) -> bool:
        current = self.read()
        object_value = current["object"]
        object_value.setdefault("GeneralOptions", {})["CatchupMode"] = bool(enabled)
        body = {
            "ClientLocale": "zh-cn",
            "CommandId": "PageSave",
            "Data": json.dumps(object_value, ensure_ascii=False, separators=(",", ":")),
            "ItemId": current.get("plugin_id"),
            "PageId": current.get("page_id") or self.page_id,
        }
        self.http.request(
            "POST",
            f"{self.base_url}/emby/UI/Command?{urlencode({'X-Emby-Token': self.token})}",
            headers=self._headers(),
            json_body=body,
            accepted=(200, 204),
        )
        verified = self.read()["enabled"]
        if verified != bool(enabled):
            raise ExternalControlError("追更开关保存后验证不一致")
        return verified


class ScanSystemClient:
    """Control the external scan switch and request the target Emby refresh."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        setting_name: str,
        target_name: str,
        *,
        http: Optional[JsonHttpClient] = None,
    ):
        self.base_url = str(base_url or "").rstrip("/")
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self.setting_name = str(setting_name or "").strip()
        self.target_name = str(target_name or "").strip()
        self.http = http or JsonHttpClient()
        self._token = ""
        self._token_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return bool(
            self.base_url
            and self.username
            and self.password
            and self.setting_name
            and self.target_name
        )

    def login(self) -> str:
        if not self.ready:
            raise ExternalControlError("外部扫库配置不完整")
        _status, payload = self.http.request(
            "POST",
            f"{self.base_url}/api/v1/login/access-token",
            form_body={"username": self.username, "password": self.password},
        )
        token = str((payload or {}).get("access_token") or "") if isinstance(payload, dict) else ""
        if not token:
            raise ExternalControlError("外部扫库登录未返回 access_token")
        with self._token_lock:
            self._token = token
        return token

    def _authorized_request(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        retry: bool = True,
    ) -> Any:
        with self._token_lock:
            token = self._token
        if not token:
            token = self.login()
        try:
            _status, payload = self.http.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json_body=json_body,
                accepted=(200, 201, 204),
            )
            return payload
        except ExternalControlError as error:
            text = str(error)
            if retry and ("HTTP 401" in text or "HTTP 403" in text):
                with self._token_lock:
                    self._token = ""
                self.login()
                return self._authorized_request(
                    method, url, json_body=json_body, retry=False
                )
            raise

    @staticmethod
    def _settings(payload: Any) -> list:
        if isinstance(payload, list):
            return copy.deepcopy(payload)
        if isinstance(payload, dict):
            for key in ("settings", "message"):
                if isinstance(payload.get(key), list):
                    return copy.deepcopy(payload[key])
        raise ExternalControlError("扫库配置返回格式无效")

    def read(self) -> Dict[str, Any]:
        if not self.ready:
            raise ExternalControlError("外部扫库配置不完整")
        payload = self._authorized_request(
            "GET",
            f"{self.base_url}/api/v1/system/settings/{quote(self.setting_name, safe='')}",
        )
        settings = self._settings(payload)
        node = next(
            (row for row in settings if str(row.get("name") or "") == self.target_name),
            None,
        )
        if not node:
            raise ExternalControlError(f"扫库配置中找不到节点：{self.target_name}")
        return {
            "enabled": _bool_value(node.get("switch")),
            "node": copy.deepcopy(node),
            "settings": settings,
        }

    def set_enabled(self, enabled: bool) -> bool:
        current = self.read()
        settings = current["settings"]
        matched = False
        for row in settings:
            if str(row.get("name") or "") == self.target_name:
                row["switch"] = bool(enabled)
                matched = True
                break
        if not matched:
            raise ExternalControlError(f"扫库配置中找不到节点：{self.target_name}")
        self._authorized_request(
            "POST",
            f"{self.base_url}/api/v1/system/save_settings",
            json_body={"settings": settings, "name": self.setting_name},
        )
        verified = self.read()["enabled"]
        if verified != bool(enabled):
            raise ExternalControlError("扫库开关保存后验证不一致")
        return verified

    def request_emby_refresh(self) -> Dict[str, str]:
        node = self.read()["node"]
        host = str(node.get("host") or "").rstrip("/")
        api_key = str(node.get("api_key") or "").strip()
        if not host or not api_key:
            raise ExternalControlError("扫库节点缺少 Emby host 或 api_key")
        self.http.request(
            "POST",
            f"{host}/emby/Library/Refresh?{urlencode({'api_key': api_key})}",
            accepted=(200, 202, 204),
        )
        return {
            "host": host,
            "node_name": str(node.get("name") or self.target_name),
            "server_id": str(node.get("server_id") or node.get("serverId") or ""),
        }


@dataclass
class ExternalSwitchSnapshot:
    catchup_enabled: bool
    scan_enabled: bool


class ExternalControlBundle:
    """Coordinate both switches as one import-batch guard."""

    def __init__(self, catchup: CatchupSwitchClient, scan: ScanSystemClient):
        self.catchup = catchup
        self.scan = scan

    @property
    def ready(self) -> bool:
        return self.catchup.ready and self.scan.ready

    def snapshot_and_disable(self) -> ExternalSwitchSnapshot:
        if not self.ready:
            raise ExternalControlError("追更或外部扫库配置不完整")
        snapshot = ExternalSwitchSnapshot(
            catchup_enabled=self.catchup.read()["enabled"],
            scan_enabled=self.scan.read()["enabled"],
        )
        self.catchup.set_enabled(False)
        try:
            self.scan.set_enabled(False)
        except Exception:
            self.catchup.set_enabled(snapshot.catchup_enabled)
            raise
        return snapshot

    def ensure_disabled(self) -> None:
        if not self.ready:
            raise ExternalControlError("追更或外部扫库配置不完整")
        self.catchup.set_enabled(False)
        self.scan.set_enabled(False)

    def restore(self, snapshot: ExternalSwitchSnapshot) -> None:
        errors = []
        try:
            self.catchup.set_enabled(snapshot.catchup_enabled)
        except Exception as error:
            errors.append(f"追更：{error}")
        time.sleep(1)
        try:
            self.scan.set_enabled(snapshot.scan_enabled)
        except Exception as error:
            errors.append(f"扫库：{error}")
        if errors:
            raise ExternalControlError("；".join(errors))
