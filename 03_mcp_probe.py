"""Talk to the FortyGuard MCP server directly (no SDK), the same way Claude Code / Cursor do.

  python 03_mcp_probe.py          -> handshake, list tools + schemas, bad-input tests (free)
  python 03_mcp_probe.py --paid   -> also calls the tools for real

MCP in one line: the client sends JSON-RPC messages ("initialize", "tools/list", "tools/call")
over HTTP POST; the server answers with JSON or a Server-Sent-Events stream.

Writes results/mcp_probe.json and results/mcp_tools.json.
"""
import json
import sys
import time

import requests

from fg_common import MCP_URL, key, save, shrink

PAID = "--paid" in sys.argv
DOCUMENTED_TOOLS = {"env_params", "heatmap", "heatmap_read", "report", "report_read", "satellite",
                    "streetview", "temperature_routing", "temperature_routing_read"}

log = []
session_id = None
_id = 0


def rpc(method, params=None, *, notify=False, auth=True, timeout=300):
    """Send one JSON-RPC message; parse JSON or SSE reply."""
    global _id, session_id
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        _id += 1
        msg["id"] = _id
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2025-06-18"}
    if auth:
        h["Authorization"] = f"Bearer {key()}"
    if session_id:
        h["Mcp-Session-Id"] = session_id
    t0 = time.time()
    r = requests.post(MCP_URL, json=msg, headers=h, timeout=timeout)
    r.encoding = "utf-8"  # SSE has no charset header; requests would guess Latin-1 and garble °
    ms = int((time.time() - t0) * 1000)
    if r.headers.get("mcp-session-id"):
        session_id = r.headers["mcp-session-id"]
    body = None
    ctype = r.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try:
                    body = json.loads(line[5:].strip())
                except ValueError:
                    pass
    elif r.content:
        try:
            body = r.json()
        except ValueError:
            body = r.text[:500]
    return {"http": r.status_code, "ms": ms, "bytes": len(r.content), "ctype": ctype,
            "www_authenticate": r.headers.get("www-authenticate"), "body": body}


def step(name, res):
    b = res.get("body") or {}
    err = b.get("error") if isinstance(b, dict) else None
    is_err = (b.get("result") or {}).get("isError") if isinstance(b, dict) else None
    print(f"{res['http']:>4} {res['ms']:>6}ms {res['bytes']:>9}B  {name}"
          + (f"  JSON-RPC error: {err.get('message')}" if err else "")
          + ("  [tool isError=true]" if is_err else ""))
    log.append({"step": name, **{k: v for k, v in res.items() if k != "body"}, "body": shrink(res.get("body"), 400)})
    return res


def tool(name, args):
    return rpc("tools/call", {"name": name, "arguments": args})


def text_of(res):
    """Pull the text/structured content out of a tool result."""
    r = (res.get("body") or {}).get("result") or {}
    if r.get("structuredContent"):
        return r["structuredContent"]
    for c in r.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except ValueError:
                return c["text"]
    return r


print("== Connection")
h = requests.get(MCP_URL.replace("/mcp", "/health"), timeout=15)
log.append({"step": "GET /health", "http": h.status_code, "body": h.json()})
print(f"{h.status_code}  /health -> {h.text}")
step("initialize WITHOUT key", rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                    "clientInfo": {"name": "probe", "version": "1"}}, auth=False))
init = step("initialize with key", rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                       "clientInfo": {"name": "fg-review-probe", "version": "1"}}))
info = (init.get("body") or {}).get("result", {})
print("   server:", info.get("serverInfo"), "protocol:", info.get("protocolVersion"))
print("   capabilities:", list((info.get("capabilities") or {}).keys()))
if info.get("instructions"):
    print("   server instructions:", info["instructions"][:300])
rpc("notifications/initialized", notify=True)

print("\n== Discovery")
tl = step("tools/list", rpc("tools/list"))
tools = ((tl.get("body") or {}).get("result") or {}).get("tools", [])
names = {t["name"] for t in tools}
print(f"   {len(tools)} tools: {sorted(names)}")
print(f"   undocumented: {sorted(names - DOCUMENTED_TOOLS)}   documented-but-missing: {sorted(DOCUMENTED_TOOLS - names)}")
for t in tools:
    props = (t.get("inputSchema") or {}).get("properties", {})
    req = (t.get("inputSchema") or {}).get("required", [])
    print(f"   - {t['name']}: required={req} all={list(props)} annotations={t.get('annotations')}")
tool_chars = len(json.dumps(tools))
print(f"   tool catalog size: {tool_chars} chars (~{tool_chars // 4} tokens of LLM context on every turn)")
save("mcp_tools.json", tools)
step("resources/list", rpc("resources/list"))
step("prompts/list", rpc("prompts/list"))

print("\n== Bad inputs (free)")
step("env_params latitude=999", tool("env_params", {"latitude": 999, "longitude": -112.074, "temperature": 35,
                                                     "date_time": {"start_date": "2025-09-20", "filter_type": 3}}))
step("env_params missing date_time", tool("env_params", {"latitude": 33.4484, "longitude": -112.074, "temperature": 35}))
step("heatmap_read unknown id", tool("heatmap_read", {"heatmap_id": "hm_does_not_exist"}))
step("report_read unknown id", tool("report_read", {"analytics_id": "does_not_exist"}))
step("temperature_routing_read unknown id", tool("temperature_routing_read", {"activity_id": "does_not_exist"}))
step("tool that does not exist", tool("monitors_list", {}))

if PAID:
    print("\n== Real tool calls")
    PHX = [[-112.0790, 33.4440], [-112.0690, 33.4440], [-112.0690, 33.4530], [-112.0790, 33.4530], [-112.0790, 33.4440]]
    r = step("env_params (docs example: Phoenix, 2025-09-20, 35C)",
             tool("env_params", {"latitude": 33.4484, "longitude": -112.074, "temperature": 35,
                                 "date_time": {"start_date": "2025-09-20", "filter_type": 3}}))
    print("   ->", json.dumps(shrink(text_of(r), 120))[:600])
    r = step("heatmap (async, no wait)", tool("heatmap", {
        "polygon_aoi": {"type": "Polygon", "coordinates": [PHX]},
        "date_time": {"start_date": "2025-07-15", "start_time": "14:00", "filter_type": 1}, "granularity": 100}))
    out = text_of(r)
    print("   ->", json.dumps(shrink(out, 120))[:600])
    hid = None
    if isinstance(out, dict):
        hid = out.get("heatmap_id") or out.get("activity_id") or (out.get("data") or {}).get("activity_id")
    if hid:
        for i in range(40):
            rr = step(f"heatmap_read #{i + 1}", tool("heatmap_read", {"heatmap_id": hid}))
            o = text_of(rr)
            st = json.dumps(o).lower()
            if "completed" in st or "failed" in st:
                print("   ->", json.dumps(shrink(o, 120))[:800])
                break
            time.sleep(10)
    r = step("satellite (point)", tool("satellite", {"sat": {"latitude": 33.4484, "longitude": -112.074},
                                                     "date_time": {"start_date": "2025-07-15", "start_time": "14:00",
                                                                   "filter_type": 1}}))
    print(f"   -> response size {r['bytes']:,} bytes (~{r['bytes'] // 4:,} tokens if fed to an LLM)")
    r = step("streetview", tool("streetview", {"latitude": 33.4484, "longitude": -112.074, "vertical_angle": 0,
                                               "horizontal_angle": 90, "back_view": False}))
    print(f"   -> response size {r['bytes']:,} bytes")
    r = step("temperature_routing (wait_for_completion)", tool("temperature_routing", {
        "origin": {"lat": 33.4484, "lon": -112.074}, "destination": {"lat": 33.4255, "lon": -111.9400},
        "departure_time": "2025-07-15T14:00:00Z", "wait_for_completion": True}))
    print("   ->", json.dumps(shrink(text_of(r), 120))[:800])
    r = step("report (wait_for_completion)", tool("report", {
        "latitude": 33.4484, "longitude": -112.074, "temperature": 40, "date": "2025-07-15",
        "analysis": ["geographic", "environmental"], "wait_for_completion": True}))
    print("   ->", json.dumps(shrink(text_of(r), 120))[:800])

save("mcp_probe.json", log)
print("\nSaved results/mcp_probe.json and results/mcp_tools.json")
