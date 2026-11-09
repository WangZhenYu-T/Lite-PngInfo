"""HTTP regression tests using generated PNGs and an isolated database."""

import http.cookiejar
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from PIL import Image, PngImagePlugin


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lite-pnginfo-test-")
        root = Path(self.temp.name)
        self.paths = patch.multiple(app, DATA_DIR=root / "data",
                                    DB_PATH=root / "data" / "favorites.sqlite3",
                                    _sessions={})
        self.paths.start()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.PNGInfoHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.paths.stop()
        self.temp.cleanup()

    def request(self, path, data=None):
        req = urllib.request.Request(self.base + path, data=data)
        with self.client.open(req, timeout=5) as response:
            return json.load(response)

    def read_png(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", json.dumps({"prompt": "a landscape", "uc": "blur",
                                            "seed": 42, "steps": 28}))
        output = io.BytesIO()
        with Image.new("RGB", (32, 48)) as image:
            image.save(output, format="PNG", pnginfo=info)
        data = output.getvalue()
        result = self.request("/api/inspect", data)
        self.assertEqual(result["metadata"]["generation"]["seed"], "42")
        self.assertEqual(result["metadata"]["file"]["height"], 48)
        return data

    def test_favorite_roundtrip_and_reset(self):
        data = self.read_png()
        favorite = self.request("/api/favorites", b"")
        favorite_id = favorite["id"]
        self.assertFalse(favorite["already_exists"])
        self.assertTrue(self.request("/api/favorites", b"")["already_exists"])
        self.assertEqual(len(self.request("/api/favorites")["favorites"]), 1)
        saved = self.request(f"/api/favorites/{favorite_id}")
        self.assertEqual(saved["metadata"]["prompts"]["negative_prompt"], "blur")
        with self.client.open(self.base + f"/api/favorites/{favorite_id}/image") as response:
            self.assertEqual(response.read(), data)
        self.request("/api/reset", b"")
        self.assertEqual(app._sessions, {})
        self.assertEqual(len(self.request("/api/favorites")["favorites"]), 1)
        self.request(f"/api/favorites/{favorite_id}/delete", b"")
        self.assertEqual(self.request("/api/favorites")["favorites"], [])

    def test_missing_database_directory_recovers(self):
        self.request("/api/favorites")
        shutil.rmtree(app.DATA_DIR)
        self.read_png()
        self.assertTrue(self.request("/api/favorites", b"")["ok"])

    def test_database_error_returns_json(self):
        app.DATA_DIR.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/favorites")
        with caught.exception as response:
            self.assertEqual(response.code, 500)
            self.assertFalse(json.load(response)["ok"])

    def test_failed_read_clears_previous_favoritable_image(self):
        self.read_png()
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/api/inspect", b"not a PNG")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/favorites", b"")
        self.assertEqual(caught.exception.code, 409)

    def test_empty_png_favorite(self):
        output = io.BytesIO()
        Image.new("RGB", (3, 5)).save(output, format="PNG")
        result = self.request("/api/inspect", output.getvalue())
        self.assertEqual(result["metadata"]["status"], "empty")
        favorite_id = self.request("/api/favorites", b"")["id"]
        saved = self.request(f"/api/favorites/{favorite_id}")
        self.assertEqual(saved["metadata"]["entries"], [])
        self.assertEqual(saved["favorite"]["source"]["label"], "无生成元信息")

    def test_v1_favorite_upgrade_preserves_original_and_backup(self):
        data = self.read_png()
        favorite_id = self.request("/api/favorites", b"")["id"]
        old_metadata = {"file": {"width": 32, "height": 48}, "raw": {"Comment": {"prompt": "old"}}}
        with closing(sqlite3.connect(app.DB_PATH)) as db, db:
            db.execute("UPDATE favorites SET metadata_json=?, prompt='old', created_at='original-date' WHERE id=?",
                       (json.dumps(old_metadata), favorite_id))
        listed = self.request("/api/favorites")["favorites"][0]
        self.assertEqual(listed["source"]["family"], "legacy")
        updated = self.request(f"/api/favorites/{favorite_id}")
        self.assertEqual(updated["metadata"]["schema_version"], 2)
        self.assertEqual(updated["metadata"]["generation"]["seed"], "42")
        self.assertEqual(updated["favorite"]["created_at"], "original-date")
        self.assertEqual(updated["favorite"]["id"], favorite_id)
        with closing(sqlite3.connect(app.DB_PATH)) as db:
            image, metadata = db.execute("SELECT image, metadata_json FROM favorites WHERE id=?", (favorite_id,)).fetchone()
        self.assertEqual(image, data)
        self.assertEqual(json.loads(metadata)["source"]["label"], "NAI")
        backup = app.DB_PATH.with_name("favorites.before-v2.sqlite3")
        with closing(sqlite3.connect(backup)) as db:
            metadata = db.execute("SELECT metadata_json FROM favorites WHERE id=?", (favorite_id,)).fetchone()[0]
        self.assertEqual(json.loads(metadata), old_metadata)
        self.assertTrue(self.request("/api/favorites", b"")["already_exists"])

    def test_unreadable_old_image_keeps_archived_result(self):
        self.read_png()
        favorite_id = self.request("/api/favorites", b"")["id"]
        old = {"file": {"width": 32, "height": 48}, "raw": {"Comment": {"prompt": "archived"}},
               "prompts": {"prompt": "archived", "negative_prompt": ""}}
        with closing(sqlite3.connect(app.DB_PATH)) as db, db:
            db.execute("UPDATE favorites SET metadata_json=?, image=? WHERE id=?",
                       (json.dumps(old), b"broken", favorite_id))
        result = self.request(f"/api/favorites/{favorite_id}")
        self.assertEqual(result["metadata"]["prompts"]["prompt"], "archived")
        self.assertEqual(result["metadata"]["entries"][0]["kind"], "archived")
        with closing(sqlite3.connect(app.DB_PATH)) as db:
            self.assertEqual(json.loads(db.execute("SELECT metadata_json FROM favorites").fetchone()[0]), old)


if __name__ == "__main__":
    unittest.main()
