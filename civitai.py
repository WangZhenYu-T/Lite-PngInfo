"""Small HTTPS hash lookup client. Only verified hash matches become model links."""

import json
import http.client
import socket
import ssl
import sys
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener, getproxies

from models import normalize_hash

API = "https://civitai.com/api/v1/model-versions/by-hash/"
MAX_RESPONSE = 2 * 1024 * 1024


def urlopen(request, timeout):
    # Re-read system/environment proxy settings on every request; urllib's global
    # opener otherwise retains the settings from the first query for this process.
    return build_opener(ProxyHandler()).open(request, timeout=timeout)


def network_failure(exc):
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        detail = "TLS 证书验证失败；请检查代理证书和系统时间。"
    elif isinstance(reason, socket.gaierror):
        detail = "DNS 无法解析 Civitai 地址。"
    elif isinstance(reason, (TimeoutError, socket.timeout)):
        detail = "连接或读取超时。"
    elif isinstance(reason, ConnectionRefusedError):
        detail = "连接被拒绝；请检查代理是否运行。"
    elif isinstance(reason, ConnectionResetError):
        detail = "连接被远端或代理重置。"
    elif isinstance(reason, ssl.SSLError):
        detail = "TLS 握手失败；请检查网络或代理。"
    elif isinstance(reason, OSError):
        code = getattr(reason, "winerror", None) or reason.errno
        detail = f"网络连接失败（系统错误 {code}）。" if code is not None else "网络连接失败（OSError）。"
    else:
        detail = f"网络连接失败（{type(reason).__name__}）。"
    proxies = getproxies()
    route = "系统/环境代理" if proxies.get("https") or proxies.get("http") else "直连（未检测到代理）"
    runtime = "Windows" if sys.platform == "win32" else "Linux / WSL" if sys.platform.startswith("linux") else sys.platform
    message = f"{detail}请求来自 {runtime}，使用{route}。"
    if runtime == "Linux / WSL" and route.startswith("直连"):
        message += " Windows 浏览器代理不会自动共享给 WSL；请使用 Windows 预览 exe 或原生 Windows 启动脚本。"
    return {"state": "network_error", "message": message}


def lookup_hash(digest):
    digest = normalize_hash(digest)
    if not digest:
        return {"state": "invalid_hash", "message": "哈希格式无效，需 8–64 位十六进制模型哈希。"}
    # WSL stores SQLite locally, while a Windows-only proxy may be inaccessible
    # from its network namespace. Delegate only this public hash request.
    windows_python = shutil.which("py.exe") if sys.platform.startswith("linux") and os.environ.get("WSL_DISTRO_NAME") else None
    if windows_python:
        try:
            script = subprocess.check_output(["wslpath", "-w", str(Path(__file__).resolve())], text=True).strip()
            completed = subprocess.run([windows_python, "-3", script, "--stdio-lookup"],
                                       input=json.dumps({"hash": digest}), capture_output=True, text=True, timeout=20)
            result = json.loads(completed.stdout)
            if completed.returncode == 0 and isinstance(result, dict) and isinstance(result.get("state"), str):
                return result
            return {"state": "network_error", "message": "Windows 网络查询进程未正常返回，请确认 Windows Python 可用。"}
        except (OSError, ValueError, subprocess.SubprocessError):
            return {"state": "network_error", "message": "无法通过 Windows Python 查询 Civitai，请检查 Windows Python 和系统代理。"}
    request = Request(API + digest, headers={"Accept": "application/json", "User-Agent": "BunnyInfo/3.0"})
    try:
        with urlopen(request, timeout=12) as response:
            body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            return {"state": "service_error", "message": "Civitai 返回内容过大，请稍后重试。"}
        data = json.loads(body)
    except HTTPError as exc:
        with exc:
            status = exc.code
            retry = exc.headers.get("Retry-After", "")
        if status == 404:
            return {"state": "not_found", "message": "Civitai 未找到此哈希对应的可见模型版本。"}
        if status in (401, 403):
            return {"state": "access_denied", "message": "Civitai 访问受限，可能需要认证或当前网络被限制。"}
        if status == 429:
            try:
                seconds = max(1, int(retry))
            except ValueError:
                try:
                    seconds = max(1, int((parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()))
                except (ValueError, TypeError, OverflowError):
                    seconds = 60
            return {"state": "rate_limited", "message": "Civitai 请求过于频繁，请稍后重试。", "retry_after": seconds}
        return {"state": "service_error", "message": f"Civitai 返回 HTTP {status}，请稍后重试。"}
    except (URLError, TimeoutError, socket.timeout, OSError, http.client.HTTPException) as exc:
        return network_failure(exc)
    except (ValueError, UnicodeError):
        return {"state": "service_error", "message": "Civitai 未返回有效的 JSON 数据。"}
    if not isinstance(data, dict):
        return {"state": "service_error", "message": "Civitai 响应结构无效。"}
    files = data.get("files", [])
    matching = [item for item in files if isinstance(item, dict) and isinstance(item.get("hashes"), dict)
                and (any(normalize_hash(value) == digest for value in item["hashes"].values())
                     or (len(digest) in (10, 12) and len(normalize_hash(item["hashes"].get("SHA256", ""))) == 64
                         and normalize_hash(item["hashes"].get("SHA256", "")).startswith(digest)))] if isinstance(files, list) else []
    model_id, version_id = data.get("modelId"), data.get("id")
    if not matching or type(model_id) is not int or type(version_id) is not int or min(model_id, version_id) <= 0:
        return {"state": "unverified", "message": "服务返回了结果，但无法核验对应文件哈希。"}
    model = data.get("model", {})
    return {"state": "matched", "message": "已匹配", "hash": digest,
            "model_name": str(model.get("name", "")) if isinstance(model, dict) else "",
            "version_name": str(data.get("name", "")), "model_id": model_id, "version_id": version_id,
            "url": f"https://civitai.com/models/{model_id}?modelVersionId={version_id}"}


class LookupClient:
    """Three in-flight HTTPS requests; identical session/hash requests share a future."""

    def __init__(self):
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(3)
        self.inflight = {}
        self.cooldown_until = 0.0

    def query(self, digest, cache, retry=False):
        digest = normalize_hash(digest)
        if not digest:
            return lookup_hash("")
        key = (id(cache), digest)
        with self.lock:
            if not retry and digest in cache:
                return {**cache[digest], "cached": True}
            future = self.inflight.get(key)
            owner = future is None
            if owner:
                future = self.inflight[key] = Future()
        if not owner:
            return future.result()
        try:
            with self.slots:
                # Check after taking a slot so queued calls also respect a newly received 429.
                with self.lock:
                    wait = self.cooldown_until - time.monotonic()
                if wait > 0:
                    result = {"state": "rate_limited", "message": "Civitai 限流冷却中，请稍后重试。", "retry_after": int(wait) + 1}
                else:
                    result = lookup_hash(digest)
                with self.lock:
                    if result["state"] == "rate_limited":
                        self.cooldown_until = max(self.cooldown_until, time.monotonic() + result.get("retry_after", 60))
                    if result["state"] == "matched":
                        if len(cache) >= 128:
                            cache.pop(next(iter(cache)))
                        cache[digest] = result
            future.set_result(result)
            return result
        except Exception as exc:
            # Wake identical-hash waiters, then expose unexpected programming errors normally.
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.inflight.pop(key, None)


if __name__ == "__main__" and sys.argv[1:] == ["--stdio-lookup"]:
    payload = json.load(sys.stdin)
    print(json.dumps(lookup_hash(payload.get("hash", "")), ensure_ascii=True))
