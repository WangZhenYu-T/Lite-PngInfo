#!/usr/bin/env python3
"""A small, dependency-light PNGInfo web application.

Run with: python app.py
Then open http://127.0.0.1:8765 in a browser.
"""

from __future__ import annotations

import base64
import hashlib
import http.cookies
import io
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import urllib.parse
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "favorites.sqlite3"
HOST = os.environ.get("PNGINFO_HOST", "127.0.0.1")
PORT = int(os.environ.get("PNGINFO_PORT", "8765"))
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

_session_lock = threading.RLock()
_sessions: dict[str, dict[str, Any]] = {}
_db_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_safe(value: Any) -> Any:
    """Convert Pillow values and arbitrary metadata into JSON-safe values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def parse_json_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def extract_prompt(metadata: dict[str, Any]) -> str:
    comment = metadata.get("Comment")
    if isinstance(comment, dict):
        return str(comment.get("prompt") or comment.get("positive_prompt") or "")
    if isinstance(comment, str):
        parsed = parse_json_text(comment)
        if isinstance(parsed, dict):
            return str(parsed.get("prompt") or parsed.get("positive_prompt") or "")
        return comment
    description = metadata.get("Description")
    return str(description or "")


def extract_negative_prompt(metadata: dict[str, Any]) -> str:
    comment = metadata.get("Comment")
    if isinstance(comment, dict):
        return str(comment.get("uc") or comment.get("negative_prompt") or "")
    if isinstance(comment, str):
        parsed = parse_json_text(comment)
        if isinstance(parsed, dict):
            return str(parsed.get("uc") or parsed.get("negative_prompt") or "")
    return ""


def normalize_metadata(image_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("无法读取该文件，请确认它是有效的 PNG 图片。") from exc

    if image.format != "PNG":
        raise ValueError("PNGInfo 只接受 PNG 图片。")

    raw_info = {str(key): json_safe(value) for key, value in image.info.items()}
    for key in ("Comment", "Description"):
        raw_info[key] = parse_json_text(raw_info.get(key))

    comment = raw_info.get("Comment")
    comment_json = comment if isinstance(comment, dict) else {}
    prompt = extract_prompt(raw_info)
    negative_prompt = extract_negative_prompt(raw_info)

    core = {
        "filename": filename,
        "format": image.format,
        "mode": image.mode,
        "width": image.width,
        "height": image.height,
        "aspect_ratio": round(image.width / image.height, 6) if image.height else None,
        "file_size_bytes": len(image_bytes),
    }
    generation = {
        key: comment_json[key]
        for key in (
            "steps",
            "height",
            "width",
            "scale",
            "cfg_rescale",
            "seed",
            "sampler",
            "noise_schedule",
            "n_samples",
            "model_name",
            "model_hash",
            "signed_hash",
            "request_type",
            "controlnet_strength",
            "controlnet_model",
            "dynamic_thresholding",
            "version",
        )
        if key in comment_json
    }

    prompt_details = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "v4_prompt": comment_json.get("v4_prompt"),
        "v4_negative_prompt": comment_json.get("v4_negative_prompt"),
    }

    return {
        "file": core,
        "generation": generation,
        "prompts": prompt_details,
        "png_text": raw_info,
        "raw": raw_info,
    }


def init_db() -> None:
    ensure_database()


def ensure_data_dir() -> None:
    """Make database operations resilient if the data folder was removed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_database() -> None:
    """Create the database directory and schema when needed."""
    ensure_data_dir()
    with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                image BLOB NOT NULL,
                prompt TEXT NOT NULL DEFAULT '',
                negative_prompt TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_favorites_sha256 ON favorites(sha256)")


def favorite_summary(row: sqlite3.Row) -> dict[str, Any]:
    metadata = json.loads(row["metadata_json"])
    file_info = metadata.get("file", {})
    return {
        "id": row["id"],
        "filename": row["filename"],
        "prompt": row["prompt"],
        "width": file_info.get("width"),
        "height": file_info.get("height"),
        "file_size_bytes": len(row["image"]),
        "created_at": row["created_at"],
    }


def list_favorites() -> list[dict[str, Any]]:
    ensure_database()
    with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM favorites ORDER BY id DESC").fetchall()
        return [favorite_summary(row) for row in rows]


class PNGInfoHandler(BaseHTTPRequestHandler):
    server_version = "PNGInfo/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._session_cookie: str | None = None
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def session_id(self) -> str:
        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        session_id = cookies.get("pnginfo_session")
        if session_id and session_id.value in _sessions:
            return session_id.value
        session_id = secrets.token_urlsafe(18)
        with _session_lock:
            _sessions[session_id] = {}
        self._session_cookie = f"pnginfo_session={session_id}; Path=/; SameSite=Lax"
        return session_id

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        if self._session_cookie:
            self.send_header("Set-Cookie", self._session_cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def send_error_json(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "app": "pnginfo"})
            return
        if parsed.path == "/api/favorites":
            try:
                self.send_json({"ok": True, "favorites": list_favorites()})
            except (OSError, sqlite3.Error):
                self.send_error_json("收藏数据库暂时不可用，请重启 PNGInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path.startswith("/api/favorites/"):
            self.get_favorite(parsed.path)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/inspect":
            self.inspect()
            return
        if parsed.path == "/api/favorites":
            self.create_favorite()
            return
        if parsed.path.startswith("/api/favorites/") and parsed.path.endswith("/delete"):
            self.delete_favorite(parsed.path)
            return
        if parsed.path == "/api/reset":
            self.reset()
            return
        self.send_error_json("接口不存在。", HTTPStatus.NOT_FOUND)

    def read_request_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("没有收到图片文件。")
        if content_length > MAX_UPLOAD_BYTES:
            raise ValueError("图片不能超过 30 MB。")
        return self.rfile.read(content_length)

    def inspect(self) -> None:
        try:
            image_bytes = self.read_request_body()
            filename = urllib.parse.unquote(self.headers.get("X-Filename", "image.png"))
            metadata = normalize_metadata(image_bytes, filename)
        except ValueError as exc:
            self.send_error_json(str(exc))
            return

        session_id = self.session_id()
        with _session_lock:
            _sessions[session_id] = {"image": image_bytes, "filename": filename, "metadata": metadata}
        self.send_json({"ok": True, "metadata": metadata, "sha256": hashlib.sha256(image_bytes).hexdigest()})

    def reset(self) -> None:
        session_id = self.session_id()
        with _session_lock:
            _sessions.pop(session_id, None)
        self.send_json({"ok": True})

    def create_favorite(self) -> None:
        session_id = self.session_id()
        with _session_lock:
            current = _sessions.get(session_id)
        if not current:
            self.send_error_json("请先读取一张图片。", HTTPStatus.CONFLICT)
            return

        metadata = current["metadata"]
        image_bytes = current["image"]
        prompt = metadata.get("prompts", {}).get("prompt", "")
        negative_prompt = metadata.get("prompts", {}).get("negative_prompt", "")
        digest = hashlib.sha256(image_bytes).hexdigest()
        try:
            ensure_database()
            with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
                existing = db.execute("SELECT id FROM favorites WHERE sha256 = ?", (digest,)).fetchone()
                if existing:
                    self.send_json({"ok": True, "id": existing[0], "already_exists": True})
                    return
                cursor = db.execute(
                    """
                    INSERT INTO favorites
                        (filename, image, prompt, negative_prompt, metadata_json, sha256, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current["filename"],
                        image_bytes,
                        prompt,
                        negative_prompt,
                        json.dumps(metadata, ensure_ascii=False),
                        digest,
                        utc_now(),
                    ),
                )
                favorite_id = cursor.lastrowid
        except (OSError, sqlite3.Error):
            self.send_error_json("收藏数据库暂时不可用，请重启 PNGInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_json({"ok": True, "id": favorite_id, "already_exists": False})

    def get_favorite(self, path: str) -> None:
        pieces = path.strip("/").split("/")
        if len(pieces) < 3:
            self.send_error_json("收藏记录不存在。", HTTPStatus.NOT_FOUND)
            return
        try:
            favorite_id = int(pieces[2])
        except ValueError:
            self.send_error_json("收藏记录不存在。", HTTPStatus.NOT_FOUND)
            return
        try:
            ensure_database()
            with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT * FROM favorites WHERE id = ?", (favorite_id,)).fetchone()
        except (OSError, sqlite3.Error):
            self.send_error_json("收藏数据库暂时不可用，请重启 PNGInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if row is None:
            self.send_error_json("收藏记录不存在。", HTTPStatus.NOT_FOUND)
            return
        if len(pieces) >= 4 and pieces[3] == "image":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(row["image"])))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(row["image"])
            return
        self.send_json({"ok": True, "metadata": json.loads(row["metadata_json"]), "favorite": favorite_summary(row)})

    def delete_favorite(self, path: str) -> None:
        pieces = path.strip("/").split("/")
        try:
            favorite_id = int(pieces[2])
        except (IndexError, ValueError):
            self.send_error_json("收藏记录不存在。", HTTPStatus.NOT_FOUND)
            return
        try:
            ensure_database()
            with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
                cursor = db.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
        except (OSError, sqlite3.Error):
            self.send_error_json("收藏数据库暂时不可用，请重启 PNGInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if cursor.rowcount == 0:
            self.send_error_json("收藏记录不存在。", HTTPStatus.NOT_FOUND)
            return
        self.send_json({"ok": True})

    def serve_static(self, path: str) -> None:
        relative = urllib.parse.unquote(path.lstrip("/")) or "index.html"
        if relative.startswith("static/"):
            relative = relative.removeprefix("static/")
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in candidate.parents and candidate != STATIC_DIR:
            self.send_error_json("资源不存在。", HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error_json("资源不存在。", HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), PNGInfoHandler)
    print(f"PNGInfo running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPNGInfo stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
