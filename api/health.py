"""GET /api/health: liveness + config check (no secrets, no LLM call)."""
import os
from http.server import BaseHTTPRequestHandler
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from paylane.http_util import send_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        provider = os.getenv("PAYLANE_PROVIDER") or ("openrouter" if os.getenv("OPENROUTER_API_KEY") else "demo")
        out = {"status": "ok", "provider": provider,
               "model": os.getenv("OPENROUTER_MODEL") if provider == "openrouter" else os.getenv("PAYLANE_MODEL"),
               "llm_key_configured": bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))}
        send_json(self, out, 200 if out["status"] == "ok" else 503)
