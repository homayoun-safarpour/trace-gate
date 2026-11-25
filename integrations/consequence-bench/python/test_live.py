import http.client
import json
import threading
import unittest

import app


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.s = app.server(0)
        c.t = threading.Thread(target=c.s.serve_forever, daemon=True)
        c.t.start()
        c.port = c.s.server_port

    @classmethod
    def tearDownClass(c):
        c.s.shutdown()
        c.s.server_close()

    def request(self, data, headers=None, path="/api/check"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request("POST", path, data, {"Content-Type": "application/json", **(headers or {})})
        r = c.getresponse()
        status = r.status
        body = r.read()
        c.close()
        return status, body

    def case(self, tool="", unknown=False, missing_hash=False):
        status, body = self.request(
            json.dumps(dict(second_tool=tool, unknown=unknown, missing_hash=missing_hash))
        )
        self.assertEqual(status, 200)
        events = [json.loads(x) for x in body.splitlines()]
        self.assertEqual(
            [x["event"] for x in events],
            ["accepted", "baseline_started", "baseline_completed", "check_started", "completed"],
        )
        self.assertEqual(len(set(x["run_id"] for x in events)), 1)
        self.assertEqual(sorted(x["at_ns"] for x in events), [x["at_ns"] for x in events])
        return events

    def test_clean(self):
        self.assertEqual(self.case()[-1]["result"]["verdict"], "PASS")

    def test_forbidden(self):
        r = self.case("deny_0")[-1]
        self.assertEqual(r["result"]["verdict"], "POLICY_VIOLATION")
        self.assertGreater(r["score"]["composite"], 0.95)

    def test_unknown(self):
        self.assertEqual(self.case(unknown=True)[-1]["result"]["verdict"], "UNKNOWN_TRAJECTORY")

    def test_missing(self):
        self.assertEqual(
            self.case(missing_hash=True)[-1]["result"]["verdict"], "MISSING_RUBRIC_FINGERPRINT"
        )

    def test_repeat_is_fresh(self):
        self.assertNotEqual(self.case()[0]["run_id"], self.case()[0]["run_id"])

    def test_cross_origin(self):
        self.assertEqual(self.request("{}", {"Origin": "https://evil.example"})[0], 403)

    def test_host(self):
        self.assertEqual(self.request("{}", {"Host": "evil.example"})[0], 403)

    def test_duplicates(self):
        self.assertEqual(
            self.request(
                '{"second_tool":"a","second_tool":"b","unknown":false,"missing_hash":false}'
            )[0],
            400,
        )

    def test_injection(self):
        self.assertEqual(
            self.request(
                json.dumps(dict(second_tool="; rm -rf /", unknown=False, missing_hash=False))
            )[0],
            400,
        )

    def test_unrecognised_fields(self):
        self.assertEqual(self.request('{"cmd":"whoami"}')[0], 400)

    def test_concurrency_guard(self):
        app.LOCK.acquire()
        try:
            self.assertEqual(
                self.request('{"second_tool":"","unknown":false,"missing_hash":false}')[0], 429
            )
        finally:
            app.LOCK.release()

    def test_static_routes(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("GET", "/")
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        self.assertIn(b"Run live check", r.read())
        c.close()

    def test_no_traversal(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("GET", "/../app.py")
        r = c.getresponse()
        self.assertEqual(r.status, 404)
        r.read()
        c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
