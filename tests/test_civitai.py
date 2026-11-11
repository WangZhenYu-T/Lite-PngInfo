import io
import json
import http.client
from pathlib import Path
import sys
import unittest
import threading
import socket
import ssl
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import civitai


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.windows_python = patch("civitai.shutil.which", return_value=None)
        self.windows_python.start()
        self.addCleanup(self.windows_python.stop)

    def response(self, data):
        return io.BytesIO(json.dumps(data).encode())

    def test_only_verified_hash_builds_safe_version_link(self):
        data = {"id": 22, "modelId": 11, "name": "v1", "model": {"name": "Example"},
                "files": [{"hashes": {"AutoV2": "abcdef0123"}}], "url": "javascript:bad"}
        with patch("civitai.urlopen", return_value=self.response(data)) as request:
            result = civitai.lookup_hash("abcdef0123")
        self.assertEqual(result["state"], "matched")
        self.assertEqual(result["url"], "https://civitai.com/models/11?modelVersionId=22")
        self.assertEqual(request.call_args.args[0].full_url, civitai.API + "ABCDEF0123")
        data["files"][0]["hashes"]["AutoV2"] = "1111111111"
        with patch("civitai.urlopen", return_value=self.response(data)):
            self.assertEqual(civitai.lookup_hash("abcdef0123")["state"], "unverified")
        data["files"][0]["hashes"] = {"SHA256": "ABCDEF012345" + "0" * 52}
        with patch("civitai.urlopen", return_value=self.response(data)):
            self.assertEqual(civitai.lookup_hash("abcdef012345")["state"], "matched")

    def test_http_errors_not_misreported_as_missing(self):
        for code, expected in [(404, "not_found"), (401, "access_denied"), (403, "access_denied"),
                               (429, "rate_limited"), (503, "service_error")]:
            with self.subTest(code=code), patch("civitai.urlopen", side_effect=HTTPError(
                    civitai.API, code, "error", {"Retry-After": "17"}, io.BytesIO())):
                result = civitai.lookup_hash("abcdef0123")
                self.assertEqual(result["state"], expected)
                if code == 429:
                    self.assertEqual(result["retry_after"], 17)

    def test_invalid_and_network_responses(self):
        with patch("civitai.urlopen") as request:
            self.assertEqual(civitai.lookup_hash("https://evil")["state"], "invalid_hash")
            request.assert_not_called()
        with patch("civitai.urlopen", side_effect=URLError("offline")):
            self.assertEqual(civitai.lookup_hash("abcdef0123")["state"], "network_error")
        with patch("civitai.urlopen", side_effect=http.client.IncompleteRead(b"{")):
            self.assertEqual(civitai.lookup_hash("abcdef0123")["state"], "network_error")
        for body in [b"<html>blocked</html>", b"[]", b"{" + b" " * civitai.MAX_RESPONSE]:
            with patch("civitai.urlopen", return_value=io.BytesIO(body)):
                self.assertEqual(civitai.lookup_hash("abcdef0123")["state"], "service_error")

    def test_cache_explicit_retry_and_cooldown(self):
        client, cache = civitai.LookupClient(), {}
        with patch("civitai.lookup_hash", return_value={"state": "matched"}) as request, patch("civitai.time.sleep"):
            client.query("abcdef0123", cache)
            self.assertTrue(client.query("ABCDEF0123", cache)["cached"])
            client.query("abcdef0123", cache, retry=True)
            self.assertEqual(request.call_count, 2)
        client = civitai.LookupClient()
        with patch("civitai.lookup_hash", return_value={"state": "rate_limited", "retry_after": 60}) as request:
            client.query("abcdef0123", {})
            self.assertEqual(client.query("1234567890", {})["state"], "rate_limited")
            self.assertEqual(request.call_count, 1)

    def test_parallel_identical_lookup_uses_one_request(self):
        client, cache, results = civitai.LookupClient(), {}, []
        entered, release = threading.Event(), threading.Event()
        def lookup(digest):
            entered.set()
            self.assertTrue(release.wait(3))
            return {"state": "matched"}
        with patch("civitai.lookup_hash", side_effect=lookup) as request:
            first = threading.Thread(target=lambda: results.append(client.query("abcdef0123", cache)))
            second = threading.Thread(target=lambda: results.append(client.query("abcdef0123", cache)))
            first.start()
            self.assertTrue(entered.wait(3))
            second.start()
            release.set()
            first.join(3)
            second.join(3)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual(request.call_count, 1)
            self.assertEqual(len(results), 2)

    def test_distinct_hashes_run_in_parallel_with_maximum_three(self):
        client, cache = civitai.LookupClient(), {}
        lock = threading.Lock()
        three_entered, release = threading.Event(), threading.Event()
        active = peak = entered = 0
        errors = []
        def lookup(digest):
            nonlocal active, peak, entered
            with lock:
                active += 1
                entered += 1
                peak = max(peak, active)
                if active == 3:
                    three_entered.set()
            if not release.wait(4):
                errors.append("parallel requests did not start")
            with lock:
                active -= 1
            return {"state": "not_found"}
        with patch("civitai.lookup_hash", side_effect=lookup):
            threads = [threading.Thread(target=lambda i=i: client.query(f"{i:010X}", cache)) for i in range(6)]
            for thread in threads:
                thread.start()
            try:
                self.assertTrue(three_entered.wait(3), "three requests must overlap")
                with lock:
                    self.assertEqual(entered, 3, "remaining requests must wait for a free slot")
            finally:
                release.set()
                for thread in threads:
                    thread.join(4)
            self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(peak, 3)
        self.assertEqual(errors, [])

    def test_request_refreshes_system_proxy_handler(self):
        request = civitai.Request(civitai.API + "ABCDEF0123")
        with patch("civitai.build_opener") as build, patch("civitai.ProxyHandler") as proxy:
            civitai.urlopen(request, timeout=12)
            civitai.urlopen(request, timeout=12)
            self.assertEqual(proxy.call_count, 2)
            self.assertEqual(build.call_count, 2)
            build.return_value.open.assert_called_with(request, timeout=12)

    def test_network_diagnostics_explain_runtime_route_and_error(self):
        with patch("civitai.sys.platform", "linux"), patch("civitai.getproxies", return_value={}):
            result = civitai.network_failure(URLError(socket.gaierror(-2, "failed")))
        self.assertIn("DNS", result["message"])
        self.assertIn("WSL", result["message"])
        self.assertIn("Windows", result["message"])
        with patch("civitai.sys.platform", "win32"), patch("civitai.getproxies", return_value={"https": "http://user:secret@127.0.0.1:7897"}):
            result = civitai.network_failure(URLError(ssl.SSLCertVerificationError(1, "bad cert")))
        self.assertIn("TLS", result["message"])
        self.assertIn("系统/环境代理", result["message"])
        self.assertNotIn("secret", result["message"])

    def test_wsl_delegates_only_hash_over_standard_input(self):
        with patch("civitai.sys.platform", "linux"), patch.dict("os.environ", {"WSL_DISTRO_NAME": "Ubuntu-D"}), \
                patch("civitai.shutil.which", return_value="/mnt/c/py.exe"), \
                patch("civitai.subprocess.check_output", return_value='C:\\source\\civitai.py\n'), \
                patch("civitai.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"state":"matched","model_id":11}'
            result = civitai.lookup_hash("abcdef0123")
        self.assertEqual(result["state"], "matched")
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"hash": "ABCDEF0123"})
        self.assertEqual(run.call_args.args[0][-1], "--stdio-lookup")


if __name__ == "__main__":
    unittest.main()
