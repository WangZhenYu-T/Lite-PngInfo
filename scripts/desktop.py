"""Shared release launcher; application code is loaded from the selected version."""

import argparse
import errno
import json
import socket
from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox
import urllib.request
import webbrowser

import app


class DesktopServer(app.ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def start_server(data_dir, port):
    app.DATA_DIR = data_dir
    app.DB_PATH = data_dir / "favorites.sqlite3"
    # v1 and v2 use the same database schema and server handler.
    data_dir.mkdir(parents=True, exist_ok=True)
    app.init_db() if hasattr(app, "init_db") else app.ensure_database()
    server = DesktopServer(("127.0.0.1", port), app.PNGInfoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join()


def smoke_test(report):
    """Exercise the actual bundled runtime with a temporary database, then exit."""
    window = tk.Tk()
    window.withdraw()
    window.update()
    window.destroy()
    with tempfile.TemporaryDirectory(prefix="pnginfo-release-test-") as folder:
        server, thread = start_server(Path(folder), 0)
        base = f"http://127.0.0.1:{server.server_port}"
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(), urllib.request.ProxyHandler({}))
        def request(path, data=None):
            with client.open(urllib.request.Request(base + path, data=data), timeout=10) as response:
                return response.read()
        try:
            assert b"PNGInfo" in request("/")
            assert b"const state" in request("/static/app.js")
            assert json.loads(request("/api/health"))["ok"]
            # Generate a valid PNG with the bundled Pillow, not the build interpreter.
            import io
            from PIL import Image, PngImagePlugin
            output = io.BytesIO()
            info = PngImagePlugin.PngInfo()
            info.add_text("Comment", json.dumps({"prompt": "release smoke", "uc": "blur", "seed": 42}))
            Image.new("RGB", (3, 5)).save(output, format="PNG", pnginfo=info)
            data = output.getvalue()
            result = json.loads(request("/api/inspect", data))
            assert result["metadata"]["prompts"]["prompt"] == "release smoke"
            favorite = json.loads(request("/api/favorites", b""))["id"]
            assert request(f"/api/favorites/{favorite}/image") == data
            assert json.loads(request(f"/api/favorites/{favorite}"))["ok"]
            assert json.loads(request("/api/reset", b""))["ok"]
            assert len(json.loads(request("/api/favorites"))["favorites"]) == 1
            assert json.loads(request(f"/api/favorites/{favorite}/delete", b""))["ok"]
            assert json.loads(request("/api/favorites"))["favorites"] == []
        finally:
            stop_server(server, thread)
    Path(report).write_text(json.dumps({"ok": True, "checks": ["GUI runtime", "static assets", "health",
        "PNG parse", "favorite roundtrip", "reset", "delete", "clean shutdown"]}), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", metavar="REPORT")
    parser.add_argument("--launcher-test", metavar="REPORT")
    options = parser.parse_args()
    if options.smoke_test:
        smoke_test(options.smoke_test)
        return
    window = tk.Tk()
    window.title("Lite-PngInfo")
    window.resizable(False, False)
    directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(app.__file__).resolve().parent
    temporary = tempfile.TemporaryDirectory(prefix="pnginfo-launcher-test-") if options.launcher_test else None
    data_dir = Path(temporary.name) / "data" if temporary else directory / "data"
    try:
        try:
            server, thread = start_server(data_dir, 8765)
        except OSError as exc:
            # Only retry bind failures. Other file/database errors must be reported.
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES) and getattr(exc, "winerror", None) not in (10048, 10013):
                raise
            server, thread = start_server(data_dir, 0)
    except (OSError, app.sqlite3.Error) as exc:
        messagebox.showerror("Lite-PngInfo", f"Cannot start / 无法启动\n{exc}\n\nExtract to a writable folder.\n请完整解压到可写目录。")
        window.destroy()
        return
    url = f"http://127.0.0.1:{server.server_port}"
    tk.Label(window, text="Lite-PngInfo is running / 正在运行", font=("", 13)).pack(padx=28, pady=(20, 8))
    tk.Label(window, text=url).pack(padx=28, pady=4)
    tk.Label(window, text="Closing this window stops the app.\n关闭此窗口即可退出程序。", fg="#555555").pack(padx=28, pady=8)
    tk.Button(window, text="Open browser / 打开浏览器", command=lambda: webbrowser.open(url)).pack(pady=5)
    def close():
        stop_server(server, thread)
        window.destroy()
    tk.Button(window, text="Exit / 退出", command=close).pack(pady=(4, 18))
    window.protocol("WM_DELETE_WINDOW", close)
    if options.launcher_test:
        opened = []
        webbrowser.open = lambda address: opened.append(address)
        def verify_and_close():
            try:
                client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with client.open(url + "/api/health", timeout=10) as response:
                    assert json.load(response)["ok"]
                assert opened == [url]
                assert app.DB_PATH.is_file()
                Path(options.launcher_test).write_text(json.dumps({"ok": True, "browser_url": url}), encoding="utf-8")
            finally:
                close()
        window.after(800, verify_and_close)
    window.after(100, lambda: webbrowser.open(url))
    window.mainloop()
    if temporary:
        temporary.cleanup()


if __name__ == "__main__":
    main()
