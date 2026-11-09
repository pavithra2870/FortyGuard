"""Shared helpers: load the API key, make HTTP calls, record results (key always redacted)."""
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

API_BASE = "https://api.fortyguard.com"
MCP_URL = "https://tos-mcp.app.fortyguard.com/mcp"

KEY_NAMES = ("FORTYGUARD_API_KEY", "FG_API_KEY", "API_KEY", "FORTYGUARD_KEY")


def load_key():
    """Read the key from the environment or ./.env. Never prints it."""
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name].strip()
    env = ROOT / ".env"
    if env.exists():
        pairs = {}
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            pairs[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
        for name in KEY_NAMES:
            if pairs.get(name):
                return pairs[name]
        if len(pairs) == 1:  # a single unnamed-ish key in .env
            return next(iter(pairs.values()))
    raise SystemExit("No API key found. Put FORTYGUARD_API_KEY=... in .env")


_KEY = None


def key():
    global _KEY
    if _KEY is None:
        _KEY = load_key()
    return _KEY


def redact(obj):
    """Remove the API key and signed URLs from anything we save."""
    s = json.dumps(obj, default=str)
    if _KEY:
        s = s.replace(_KEY, "<REDACTED_KEY>")
    s = re.sub(r'(https?://[^"\s]*?[?&](X-Amz-Signature|Signature|sig|token)=)[^"\s&]+', r"\1<REDACTED>", s)
    return json.loads(s)


def shrink(obj, max_str=200, max_list=5):
    """Make big payloads (base64 images, GeoJSON) readable in reports."""
    if isinstance(obj, dict):
        return {k: shrink(v, max_str, max_list) for k, v in obj.items()}
    if isinstance(obj, list):
        out = [shrink(v, max_str, max_list) for v in obj[:max_list]]
        if len(obj) > max_list:
            out.append(f"... (+{len(obj) - max_list} more items)")
        return out
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + f"... ({len(obj)} chars)"
    return obj


def call(method, path, *, json_body=None, params=None, headers=None, auth=True, timeout=60):
    """One REST call. Returns a dict with status, latency, size and parsed body."""
    h = {"Content-Type": "application/json"}
    if auth:
        h["api-key"] = key()
    h.update(headers or {})
    t0 = time.time()
    try:
        r = requests.request(method, API_BASE + path, json=json_body, params=params, headers=h, timeout=timeout)
    except requests.RequestException as e:
        return {"status": None, "error": str(e), "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    try:
        body = r.json()
    except ValueError:
        body = r.text[:500]
    return {"status": r.status_code, "ms": ms, "bytes": len(r.content), "body": body,
            "content_type": r.headers.get("content-type")}


def save(name, data):
    path = RESULTS / name
    path.write_text(json.dumps(redact(data), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
