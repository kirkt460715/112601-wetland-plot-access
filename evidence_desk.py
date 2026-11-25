"""养护协作中的合成资料与合作方查询服务。"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

DATA = Path(__file__).resolve().parent / "data"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class EvidenceDesk(ThreadingHTTPServer):
    def __init__(self, port, folder=DATA):
        self.register = read_json(folder / "register.json")
        self.messages = read_json(folder / "messages.json")
        self.partner_queries = {}
        for example in read_json(folder / "partner-queries.json"):
            key = (example["action"], example["desk"])
            if key in self.partner_queries:
                raise ValueError("合作方查询样例重复")
            self.partner_queries[key] = example
        if not isinstance(self.register, dict) or any(
            row["sequence"] != i for i, row in enumerate(self.messages, 1)
        ):
            raise ValueError("台账应为对象，消息序号应连续")
        self.transient_failures = set()
        self.requests_lock = Lock()
        super().__init__(("127.0.0.1", port), EvidenceHandler)


class EvidenceHandler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        route = urlsplit(self.path)
        query = parse_qs(route.query, keep_blank_values=True)
        if route.path == "/register":
            self.respond(200, self.server.register)
        elif route.path == "/messages":
            self.read_messages(query)
        elif route.path == "/partner":
            self.read_partner(query)
        else:
            self.respond(404, {"status": "not_found"})

    def read_messages(self, query):
        try:
            after = int(query.get("after", ["0"])[0])
            size = int(query.get("size", ["30"])[0])
            if after < 0 or not 1 <= size <= 100:
                raise ValueError
        except ValueError:
            self.respond(400, {"status": "bad_window"})
            return
        page = self.server.messages[after:after + size]
        self.respond(200, {"messages": page, "cursor": page[-1]["sequence"] if page else after})

    def read_partner(self, query):
        key = (query.get("action", [""])[0], query.get("desk", [""])[0])
        record = self.server.partner_queries.get(key)
        if record is None:
            self.respond(404, {"status": "unknown_request"})
            return
        with self.server.requests_lock:
            unavailable = record["unavailable_first"] and key not in self.server.transient_failures
            if unavailable:
                self.server.transient_failures.add(key)
        if unavailable:
            self.respond(503, {"status": "temporarily_unavailable"})
            return
        self.respond(200, {"fact": record["fact"]})

    def log_message(self, *args):
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    with EvidenceDesk(args.port, args.data) as server:
        print(f"资料台 http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
