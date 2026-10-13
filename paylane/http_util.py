"""Shared helpers for the API gateway functions (api/*.py)."""
import json


def send_json(h, data, status=200, cache=None):
    h.send_response(status)
    h.send_header('Content-Type', 'application/json')
    h.send_header('Access-Control-Allow-Origin', '*')
    if cache: h.send_header('Cache-Control', cache)
    h.end_headers()
    h.wfile.write(json.dumps(data).encode())
