"""Keep application data on WSL; open Windows browser only once server is bound."""

from pathlib import Path
import errno
import argparse
import json
import threading
import urllib.request
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--startup-test", metavar="REPORT")
    options = parser.parse_args()
    app.ensure_database()
    try:
        server = app.ThreadingHTTPServer(("127.0.0.1", app.PORT), app.BunnyInfoHandler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.BunnyInfoHandler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"BunnyInfo: {url}\nClose this window or press Ctrl+C to stop.", flush=True)
    if options.startup_test:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with client.open(url + "/api/favorites", timeout=10) as response:
                favorites = json.load(response)
            req = urllib.request.Request(url + "/api/models/lookup", data=b'{"hash":"DC4C67171E"}')
            with client.open(req, timeout=25) as response:
                result = json.load(response)
            Path(options.startup_test).write_text(json.dumps({"favorites_readable": favorites["ok"],
                "favorites_count": len(favorites["favorites"]), "lookup": result["result"],
                "database": str(app.DB_PATH), "url": url}), encoding="utf-8")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        return
    if options.open_browser:
        subprocess.run(["cmd.exe", "/c", "start", "", url], check=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
