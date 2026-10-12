"""Vercel serverless function for serving eval results."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        try:
            # Find transcripts directory
            base = Path(__file__).parent.parent
            transcripts_dir = base / 'transcripts'
            
            if not transcripts_dir.exists():
                self._send_json({'error': 'No eval results found'}, 404)
                return
            
            # Load all transcript JSON files
            results = []
            for file in sorted(transcripts_dir.glob('*.json')):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        results.append(data)
                except Exception as e:
                    print(f"Error loading {file}: {e}")
            
            # Calculate score
            passed = sum(1 for r in results if all(c['pass'] for c in r.get('checks', [])))
            total = len(results)
            
            self._send_json({
                'results': results,
                'score': {'passed': passed, 'total': total}
            })

        except Exception as e:
            self._send_json({'error': str(e)}, 500)
