#!/usr/bin/env python3
"""只访问回环 HTTP 服务的可执行文件回归，不访问任何 Cloudflare 目标。"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "LOCAL_TEST_SECRET_NOT_FOR_LOGS"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def do_OPTIONS(self):
        self.respond()

    def respond(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.seen.append({"path": self.path, "method": self.command, "headers": self.headers, "body": body})
        status = {"/bad": 403, "/auth": 401, "/rate": 429, "/redirect": 302}.get(self.path, 200)
        self.send_response(status)
        if self.path == "/login":
            self.send_header("Set-Cookie", "session=local; Path=/account; HttpOnly")
        if self.path == "/challenge":
            self.send_header("cf-mitigated", "challenge")
        if self.path == "/redirect":
            self.send_header("Location", "/unexpected-redirect")
        payload = json.dumps({"token": TOKEN}).encode()
        if self.path == "/large":
            payload = b"x" * 1024
        self.send_header("Content-Length", str(len(payload) + (100 if self.path == "/truncated" else 0)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.seen = []
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cfsolve-test-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.server.seen.clear()

    def invoke(self, requests, extra=None, out=False, env=None):
        spec = {"base_url": self.base + "/root/", "page_url": "https://page.example/form?private=1", "clearance": "none", "min_interval_ms": 0, "requests": requests}
        spec.update(extra or {})
        (self.dir / "spec.json").write_text(json.dumps(spec))
        command = [str(ARGS.binary), "--profile", str(ARGS.profile), "--spec", str(self.dir / "spec.json")]
        if out:
            command += ["--out", str(self.dir / "out")]
        return subprocess.run(command, text=True, capture_output=True, timeout=20, env=dict(os.environ, **(env or {})))

    def test_json_headers_body_and_no_secret_in_summary(self):
        result = self.invoke([{"method": "POST", "path": "/api", "body": {"hello": "世界"}, "headers": {"Origin": "https://page.example", "Accept-Language": "zh-CN"}}])
        self.assertEqual(result.returncode, 0, result.stderr)
        item = self.server.seen[0]
        self.assertEqual(item["headers"].get_all("Content-Type"), ["application/json"])
        self.assertEqual(item["headers"].get_all("Origin"), ["https://page.example"])
        self.assertEqual(item["headers"].get_all("Accept-Language"), ["zh-CN"])
        self.assertEqual(json.loads(item["body"]), {"hello": "世界"})
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertNotIn("private=1", str(item["headers"]))

    def test_form_content_type_and_options_method(self):
        result = self.invoke([{"method": "POST", "path": "/form", "raw_body": "a=1", "content_type": "application/x-www-form-urlencoded"}, {"method": "OPTIONS", "path": "/api"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.seen[0]["headers"].get_all("Content-Type"), ["application/x-www-form-urlencoded"])
        self.assertEqual(self.server.seen[1]["method"], "OPTIONS")

    def test_cookie_jar_persists_and_path_restriction_is_retained(self):
        result = self.invoke([{"path": "/login"}, {"path": "/account/me"}, {"path": "/outside"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("session=local", self.server.seen[1]["headers"].get("Cookie", ""))
        self.assertNotIn("session=local", self.server.seen[2]["headers"].get("Cookie", ""))

    def test_failure_challenge_and_rate_limit_stop_remaining_requests(self):
        for path in ["/bad", "/challenge", "/rate", "/redirect"]:
            with self.subTest(path=path):
                self.server.seen.clear()
                result = self.invoke([{"path": path}, {"path": "/must-not-run"}])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual([i["path"] for i in self.server.seen], [path])

    def test_expected_401_is_distinguished_from_business_success(self):
        result = self.invoke([{"path": "/auth", "expect_status": [401]}])
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout.splitlines()[0])
        self.assertEqual(summary["status"], 401)
        self.assertTrue(summary["expected_status"])
        self.assertNotIn("business_success", summary)

    def test_invalid_second_request_is_rejected_before_any_network(self):
        result = self.invoke([{"path": "/ok"}, {"method": "MISSPELLED", "path": "/bad"}])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.server.seen, [])

    def test_response_size_and_read_failures_are_errors(self):
        for path in ["/large", "/truncated"]:
            with self.subTest(path=path):
                self.server.seen.clear()
                result = self.invoke([{"path": path}, {"path": "/must-not-run"}], {"max_response_bytes": 100})
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(len(self.server.seen), 1)

    def test_private_output_and_no_overwrite(self):
        result = self.invoke([{"path": "/ok"}], out=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        directory = self.dir / "out"
        response = directory / "0000.body"
        self.assertIn(TOKEN, response.read_text())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(response.stat().st_mode), 0o600)
        self.server.seen.clear()
        result = self.invoke([{"path": "/ok"}], out=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.server.seen, [])

    def test_implicit_environment_proxy_is_not_used(self):
        result = self.invoke([{"path": "/ok"}], env={"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cookie_file_import_keeps_secure_attribute(self):
        path = self.dir / "cookies.json"
        path.write_text(json.dumps([{"origin": self.base, "set_cookie": "secure=secret; Secure; Path=/"}]))
        result = self.invoke([{"path": "/ok"}], {"cookies_file": "cookies.json"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("secure=", self.server.seen[0]["headers"].get("Cookie", ""))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=lambda x: Path(x).resolve(), required=True)
    parser.add_argument("--profile", type=lambda x: Path(x).resolve(), required=True)
    ARGS, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__] + remaining)
