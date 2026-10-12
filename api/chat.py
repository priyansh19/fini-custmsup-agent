"""Vercel serverless function for chat API."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from paylane.agent import Agent
from paylane.data import Store
from paylane.providers import ScriptedProvider, from_env

import base64, hashlib, hmac

# Serverless functions keep no reliable memory between requests, and a shared
# in-memory "default" session would leak one visitor's verified chat to another.
# So conversation state round-trips through the client as an HMAC-signed blob:
# the client can store it but cannot forge verification, refunds or tool results.
os.environ.setdefault("OPENROUTER_RETRIES", "3")   # stay inside the 60s function limit
MAX_STATE_BYTES = 400_000


def _secret() -> bytes:
    s = os.getenv("SESSION_SECRET") or ("paylane-state:" + (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "dev-only"))
    return hashlib.sha256(s.encode()).digest()


def sign_state(state: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(state, default=str).encode()).decode()
    mac = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + mac


def verify_state(token):
    if not token or not isinstance(token, str) or len(token) > MAX_STATE_BYTES or "." not in token:
        return None
    raw, mac = token.rsplit(".", 1)
    if not hmac.compare_digest(mac, hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()):
        return None
    return json.loads(base64.urlsafe_b64decode(raw.encode()))


class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self._send_json({})

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body) if body else {}
            except ValueError:
                self._send_json({'error': 'Body must be JSON: {"message": "..."}'}, 400)
                return
            if not isinstance(data, dict):
                self._send_json({'error': 'Body must be a JSON object'}, 400)
                return
            
            message = data.get('message') if isinstance(data, dict) else None
            if not isinstance(message, str) or not message.strip():
                self._send_json({'error': 'Message required'}, 400)
                return
            message = message.strip()

            # Get configuration from request
            config = data.get('config', {}) if isinstance(data, dict) else {}
            model = config.get('model')
            provider_name = config.get('provider')
            temperature = config.get('temperature', 0)
            
            # Override environment variables temporarily if config specified
            if model and provider_name:
                if provider_name == 'OpenRouter':
                    os.environ['PAYLANE_PROVIDER'] = 'openrouter'
                    os.environ['OPENROUTER_MODEL'] = model
                elif provider_name == 'OpenAI':
                    os.environ['PAYLANE_PROVIDER'] = 'openai'
                    os.environ['PAYLANE_MODEL'] = model
                elif provider_name == 'Anthropic':
                    os.environ['PAYLANE_PROVIDER'] = 'anthropic'
                    os.environ['PAYLANE_MODEL'] = model
                elif provider_name == 'Ollama (Local)':
                    os.environ['PAYLANE_PROVIDER'] = 'ollama'
                    os.environ['PAYLANE_MODEL'] = model
            
            has_key = any(os.getenv(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"))
            if has_key:
                provider, demo_mode = from_env(), False
            else:
                from evals.scenarios import SCENARIOS
                provider, demo_mode = ScriptedProvider(SCENARIOS[0]["script"]), True

            agent = Agent(provider, Store())
            if data.get('state'):
                state = verify_state(data.get('state'))
                if state is None:
                    self._send_json({'error': 'Invalid or tampered session state. Please start a new chat.'}, 400)
                    return
                agent.load_state(state)

            try:
                reply = agent.send(message)
                
                # Filter messages for customer-facing UI: only user and assistant with actual text content
                filtered_messages = [
                    m for m in agent.messages 
                    if m.get('role') in ('user', 'assistant') and m.get('content', '').strip()
                ]
                
                self._send_json({
                    'reply': reply,
                    'messages': filtered_messages,
                    'tool_calls': [
                        {'name': name, 'arguments': args, 'result': result}
                        for name, args, result in agent.store.calls
                    ],
                    'state': sign_state(agent.to_state()),
                    'demo_mode': demo_mode
                })
            except Exception as e:
                import traceback
                traceback.print_exc()  # Log to server console for debugging
                self._send_json({'error': "Our assistant is busy right now. Please try again in a moment.",
                                 'state': data.get('state')}, 503)
                return

        except Exception as e:
            import traceback
            traceback.print_exc()  # Log to server console for debugging
            self._send_json({'error': 'Internal error'}, 500)

    def do_DELETE(self):
        """Stateless: the client just drops its state blob."""
        self._send_json({'status': 'reset'})

    def do_GET(self):
        self._send_json({'error': 'Use POST to send messages'}, 405)
