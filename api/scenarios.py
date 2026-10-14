"""GET /api/scenarios: personas (mock bank customers), scenario cards and policy constants."""
from http.server import BaseHTTPRequestHandler
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paylane.http_util import send_json  # noqa: E402
from paylane.catalog import catalog


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        mode = (parse_qs(urlparse(self.path).query).get("mode") or [None])[0]
        send_json(self, catalog(mode), cache='s-maxage=300')
