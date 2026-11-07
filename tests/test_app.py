"""HTTP regression tests using generated PNGs and an isolated database."""

import http.cookiejar
import io
import json
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
        self.assertEqual(result["metadata"]["generation"]["seed"], 42)
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


if __name__ == "__main__":
    unittest.main()
