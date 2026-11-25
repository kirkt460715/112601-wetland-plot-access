from http.client import HTTPConnection
import json
from threading import Thread
from urllib.parse import urlencode
import unittest

from evidence_desk import EvidenceDesk


class EvidenceDeskContractTest(unittest.TestCase):
    def setUp(self):
        self.server = EvidenceDesk(0)
        self.addCleanup(self.server.server_close)
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def read(self, route):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request("GET", route)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_register_and_message_sequence(self):
        self.assertEqual(self.read("/register"), (200, self.server.register))
        status, page = self.read("/messages?after=0&size=2")
        self.assertEqual(status, 200)
        self.assertEqual(page["cursor"], 2)
        self.assertEqual(len(page["messages"]), 2)
        status, rest = self.read("/messages?after=2")
        self.assertEqual(status, 200)
        self.assertTrue(rest["messages"])
        self.assertEqual(page["messages"] + rest["messages"], self.server.messages)
        self.assertEqual(self.read("/messages?size=abc")[0], 400)

    def test_partner_evidence_and_unavailable_result(self):
        self.assertTrue(self.server.partner_queries)
        for (action, desk), record in self.server.partner_queries.items():
            with self.subTest(action=action, desk=desk):
                route = "/partner?" + urlencode({"action": action, "desk": desk})
                if record["unavailable_first"]:
                    self.assertEqual(self.read(route), (503, {"status": "temporarily_unavailable"}))
                expected = (200, {"fact": record["fact"]})
                self.assertEqual(self.read(route), expected)
                self.assertEqual(self.read(route), expected)
        self.assertEqual(self.read("/partner?action=unknown")[0], 404)


if __name__ == "__main__":
    unittest.main()
