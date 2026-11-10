#!/usr/bin/env python3
"""A small, dependency-light BunnyInfo web application.

Run with: python app.py
Then open http://127.0.0.1:8765 in a browser.
"""

from __future__ import annotations

import hashlib
import http.cookies
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

from metadata import PARSER_VERSION, SCHEMA_VERSION, normalize_metadata


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "favorites.sqlite3"
HOST = os.environ.get("BUNNYINFO_HOST", os.environ.get("PNGINFO_HOST", "127.0.0.1"))
PORT = int(os.environ.get("BUNNYINFO_PORT", os.environ.get("PNGINFO_PORT", "8765")))
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

_session_lock = threading.RLock()
_sessions: dict[str, dict[str, Any]] = {}
_db_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_database() -> None:
    """Create the database directory and schema when needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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


def favorite_summary(row: sqlite3.Row, metadata: dict | None = None) -> dict[str, Any]:
    metadata = metadata if metadata is not None else json.loads(row["metadata_json"])
    file_info = metadata.get("file", {})
    return {
        "id": row["id"],
        "filename": row["filename"],
        "prompt": row["prompt"],
        "width": file_info.get("width"),
        "height": file_info.get("height"),
        "source": metadata.get("source", {"family": "legacy", "label": "待更新分类"}),
        "status": metadata.get("status", "legacy"),
        "created_at": row["created_at"],
    }


def list_favorites() -> list[dict[str, Any]]:
    ensure_database()
    with _db_lock, closing(sqlite3.connect(DB_PATH)) as db, db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id, filename, prompt, metadata_json, created_at FROM favorites ORDER BY id DESC").fetchall()
        return [favorite_summary(row) for row in rows]


def favorite_metadata(row: sqlite3.Row) -> dict[str, Any]:
    """Upgrade one saved result from its original PNG; keep a one-time SQLite backup."""
    metadata = json.loads(row["metadata_json"])
    if metadata.get("schema_version") == SCHEMA_VERSION and metadata.get("parser_version") == PARSER_VERSION:
        return metadata
    try:
        updated = normalize_metadata(row["image"], row["filename"])
    except ValueError:
        # The archived result remains readable even if its stored PNG cannot be reparsed.
        raw = metadata.get("raw", metadata.get("png_text", {}))
        return {"file": metadata["file"], "source": {"family": "legacy", "label": "历史解析结果"},
                "status": "unclassified", "generation": metadata.get("generation", {}),
                "prompts": {**metadata.get("prompts", {}), "characters": []},
                "models": [], "loras": [], "image_info": {},
                "entries": [{"index": i, "key": key, "text": "", "kind": "archived",
                             "formatted": json.dumps(value, ensure_ascii=False, indent=2)}
                            for i, (key, value) in enumerate(raw.items())],
                "notes": ["原图无法重新解析，正在显示历史结果；历史字段不提供复制原文。"]}
    with _db_lock, closing(sqlite3.connect(DB_PATH)) as db:
        backup = DB_PATH.with_name(DB_PATH.stem + ".before-v2.sqlite3")
        if not backup.exists():
            with closing(sqlite3.connect(backup)) as target:
                db.backup(target)
        with db:
            db.execute("UPDATE favorites SET metadata_json = ?, prompt = ?, negative_prompt = ? WHERE id = ?",
                       (json.dumps(updated, ensure_ascii=False), updated["prompts"]["prompt"],
                        updated["prompts"]["negative_prompt"], row["id"]))
    return updated


class BunnyInfoHandler(BaseHTTPRequestHandler):
    server_version = "BunnyInfo/2.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._session_cookie: str | None = None
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def session_id(self) -> str:
        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        session_id = cookies.get("bunnyinfo_session") or cookies.get("pnginfo_session")
        if session_id and session_id.value in _sessions:
            return session_id.value
        session_id = secrets.token_urlsafe(18)
        with _session_lock:
            _sessions[session_id] = {}
        self._session_cookie = f"bunnyinfo_session={session_id}; Path=/; SameSite=Lax"
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
            self.send_json({"ok": True, "app": "bunnyinfo"})
            return
        if parsed.path == "/api/favorites":
            try:
                self.send_json({"ok": True, "favorites": list_favorites()})
            except (OSError, sqlite3.Error):
                self.send_error_json("收藏数据库暂时不可用，请重启 BunnyInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
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
        session_id = self.session_id()
        with _session_lock:
            _sessions[session_id] = {}
        try:
            image_bytes = self.read_request_body()
            filename = urllib.parse.unquote(self.headers.get("X-Filename", "image.png"))
            metadata = normalize_metadata(image_bytes, filename)
        except ValueError as exc:
            self.send_error_json(str(exc))
            return

        with _session_lock:
            _sessions[session_id] = {"image": image_bytes, "filename": filename, "metadata": metadata}
        self.send_json({"ok": True, "metadata": metadata})

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
            self.send_error_json("收藏数据库暂时不可用，请重启 BunnyInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
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
            self.send_error_json("收藏数据库暂时不可用，请重启 BunnyInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
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
        try:
            metadata = favorite_metadata(row)
        except (OSError, sqlite3.Error):
            self.send_error_json("收藏更新失败，原记录已保留，请重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        summary = favorite_summary(row, metadata)
        summary["prompt"] = metadata["prompts"]["prompt"]
        self.send_json({"ok": True, "metadata": metadata, "favorite": summary})

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
            self.send_error_json("收藏数据库暂时不可用，请重启 BunnyInfo 后重试。", HTTPStatus.INTERNAL_SERVER_ERROR)
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
    ensure_database()
    server = ThreadingHTTPServer((HOST, PORT), BunnyInfoHandler)
    print(f"BunnyInfo running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBunnyInfo stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
