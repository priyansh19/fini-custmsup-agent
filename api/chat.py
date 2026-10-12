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

# Session storage (in-memory, per-function instance)
# In production, use Redis/DynamoDB
_sessions = {}


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
            data = json.loads(body) if body else {}
            
            message = data.get('message', '').strip()
            if not message:
                self._send_json({'error': 'Message required'}, 400)
                return

            # Get or create session
            session_id = self.headers.get('X-Session-ID', 'default')
            if session_id not in _sessions:
                # Try to get a real LLM provider, fall back to demo mode
                try:
                    # Check for any valid API key
                    has_key = any([
                        os.getenv("OPENAI_API_KEY"),
                        os.getenv("ANTHROPIC_API_KEY"),
                        os.getenv("OPENROUTER_API_KEY")
                    ])
                    if has_key:
                        provider = from_env()
                        demo_mode = False
                    else:
                        raise KeyError("No API key set")
                except (KeyError, ModuleNotFoundError, Exception):
                    # No API key or provider package, use scripted demo
                    from evals.scenarios import SCENARIOS
                    provider = ScriptedProvider(SCENARIOS[0]["script"])
                    demo_mode = True
                
                _sessions[session_id] = {
                    'agent': Agent(provider, Store()),
                    'demo_mode': demo_mode
                }
            
            session = _sessions[session_id]
            agent = session['agent']
            
            # Send message to agent
            reply = agent.send(message)
            
            # Return full conversation + tool calls
            self._send_json({
                'reply': reply,
                'messages': agent.messages,
                'tool_calls': [
                    {'name': name, 'arguments': args, 'result': result}
                    for name, args, result in agent.store.calls
                ],
                'demo_mode': session['demo_mode']
            })

        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def do_DELETE(self):
        """Reset session"""
        session_id = self.headers.get('X-Session-ID', 'default')
        if session_id in _sessions:
            del _sessions[session_id]
        self._send_json({'status': 'reset'})

    def do_GET(self):
        self._send_json({'error': 'Use POST to send messages'}, 405)
