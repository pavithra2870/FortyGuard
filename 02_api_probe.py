"""Probe the FortyGuard REST API.

  python 02_api_probe.py            -> free checks only (auth, validation, error shapes). Costs 0 credits.
  python 02_api_probe.py --paid     -> also runs every endpoint for real and checks credit cost.

Writes results/api_probe.json and prints a short summary table.
"""
import sys
import time

from fg_common import call, key, save, shrink

PAID = "--paid" in sys.argv

# A small (~0.35 mi²) box in downtown Phoenix, AZ, as a closed polygon.
PHX = [[-112.0790, 33.4440], [-112.0690, 33.4440], [-112.0690, 33.4530],
       [-112.0790, 33.4530], [-112.0790, 33.4440]]
FC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [PHX]}}]}
BARE = {"type": "Polygon", "coordinates": [PHX]}
ONE_HOUR = {"start_date": "2025-07-15", "start_time": "14:00", "filter_type": 1}

results = []


def record(name, expect, res, note=""):
    row = {"test": name, "expected": expect, "status": res.get("status"), "ms": res.get("ms"),
           "bytes": res.get("bytes"), "note": note, "body": shrink(res.get("body"))}
    results.append(row)
    print(f"{str(res.get('status')):>5} {res.get('ms', 0):>6}ms  {name}  (expected {expect})")
    return res


def credits():
    """Remaining credits via the (POST, key-in-body) usage endpoint the docs widget uses."""
    r = call("POST", "/v1/system/fetch-api-key-usage", json_body={"api_key": key()})
    b = r.get("body") if isinstance(r.get("body"), dict) else {}
    return (b.get("credit_summary") or {}).get("cycle_remaining_credits"), r


def poll(activity_id, max_s=600, every=5):
    t0 = time.time()
    seen = []
    while time.time() - t0 < max_s:
        r = call("GET", f"/v1/status/{activity_id}")
        st = (r.get("body") or {}).get("data", {}).get("status") if isinstance(r.get("body"), dict) else None
        seen.append(st)
        if st in ("Completed", "Failed"):
            r["poll_seconds"] = int(time.time() - t0)
            r["statuses_seen"] = sorted(set(map(str, seen)))
            return r
        time.sleep(every)
    return {"status": "timeout", "poll_seconds": max_s, "statuses_seen": sorted(set(map(str, seen)))}


# ---------------------------------------------------------------- free checks
print("\n== Free checks (should cost 0 credits)")
record("no api-key header", 401, call("GET", "/v1/status/x", auth=False))
record("wrong api-key", 401, call("GET", "/v1/status/x", headers={"api-key": "not_a_real_key"}))
record("Bearer header on REST (MCP style)", "401 (docs: REST uses api-key)",
       call("GET", "/v1/status/x", auth=False, headers={"Authorization": f"Bearer {key()}"}))
record("status for unknown activity id", 404, call("GET", "/v1/status/00000000-0000-0000-0000-000000000000"))
record("unknown route /v1/nope", 404, call("GET", "/v1/nope"))
record("GET on POST-only /v1/heatmap", 405, call("GET", "/v1/heatmap"))
record("heatmap: empty body", "400/422", call("POST", "/v1/heatmap", json_body={}))
record("heatmap: bad date format", 400, call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": FC, "date_time": {"start_date": "07/15/2024", "start_time": "14:00", "filter_type": 1}}))
record("heatmap: filter_type 9", 400, call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": FC, "date_time": {**ONE_HOUR, "filter_type": 9}}))
record("heatmap: granularity 50 (not allowed)", 400, call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": FC, "date_time": ONE_HOUR, "granularity": 50}))
open_poly = {"type": "Polygon", "coordinates": [PHX[:-1]]}
record("heatmap: polygon not closed", 400, call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": open_poly, "date_time": ONE_HOUR}))
london = [[-0.13, 51.50], [-0.12, 51.50], [-0.12, 51.51], [-0.13, 51.51], [-0.13, 51.50]]
record("heatmap: outside US (London)", "400 (US only)", call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": {"type": "Polygon", "coordinates": [london]}, "date_time": ONE_HOUR}))
huge = [[-113.0, 33.0], [-111.0, 33.0], [-111.0, 34.0], [-113.0, 34.0], [-113.0, 33.0]]
record("heatmap: ~8,000 mi² area (over plan limit)", "400 + clear limit message", call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": {"type": "Polygon", "coordinates": [huge]}, "date_time": ONE_HOUR}))
record("heatmap: filter_type 4 range > 31 days", 400, call("POST", "/v1/heatmap", json_body={
    "polygon_aoi": FC, "date_time": {"start_date": "2025-06-01", "end_date": "2025-08-01", "filter_type": 4}}))
record("env_params: latitude 999", 400, call("POST", "/v1/env_params", json_body={
    "latitude": 999, "longitude": -112.07, "temperature": 35, "date_time": ONE_HOUR}))
record("env_params: unknown analysis name", 400, call("POST", "/v1/env_params", json_body={
    "latitude": 33.4484, "longitude": -112.074, "temperature": 35, "date_time": ONE_HOUR,
    "analysis": ["not_a_param"]}))
record("heat_intelligence: bad analysis value", 400, call("POST", "/v1/heat_intelligence", json_body={
    "latitude": 33.4484, "longitude": -112.074, "temperature": 95, "date": "2025-07-15", "analysis": ["weather"]}))
record("routing: origin == destination", 400, call("POST", "/v1/routing", json_body={
    "origin": {"lat": 33.4484, "lon": -112.074}, "destination": {"lat": 33.4484, "lon": -112.074},
    "departure_time": "2025-07-15T14:00:00Z"}))
record("routing: Phoenix -> Los Angeles (>200 km)", 400, call("POST", "/v1/routing", json_body={
    "origin": {"lat": 33.4484, "lon": -112.074}, "destination": {"lat": 34.0522, "lon": -118.2437},
    "departure_time": "2025-07-15T14:00:00Z"}))
record("monitors: list (docs say costs 3,500 credits!)", 200, call("GET", "/v1/monitors"))
record("GET /v1/alerts/{id} (mentioned in docs, never documented)", "404 or 200",
       call("GET", "/v1/alerts/alert_123"))
record("monitors: create with fake heatmap_id", "400/404", call("POST", "/v1/monitors", json_body={
    "heatmap_id": "heatmap_does_not_exist", "name": "probe", "boundary_geojson": BARE,
    "rules": [{"temporal_aggregation": "average", "spatial_aggregation": "maximum", "operator": "above",
               "threshold": 40, "unit": "celsius"}], "notifications": {"email": ["probe@example.com"]}}))
c, raw = credits()
record("credits usage endpoint (POST, key in JSON body)", 200, raw, note=f"remaining={c}")

# ---------------------------------------------------------------- paid checks
if PAID:
    print("\n== Paid checks (real jobs; we compare credits before/after with the documented cost)")
    jobs = [
        ("env_params", "/v1/env_params", {"latitude": 33.4484, "longitude": -112.074, "temperature": 35,
                                          "date_time": {"start_date": "2025-09-20", "filter_type": 3}}, 2900),
        ("heatmap (FeatureCollection AOI)", "/v1/heatmap", {"polygon_aoi": FC, "date_time": ONE_HOUR,
                                                            "granularity": 100}, 4220),
        ("heatmap (bare Polygon AOI, as in endpoint example)", "/v1/heatmap",
         {"polygon_aoi": BARE, "date_time": ONE_HOUR, "granularity": 100}, 4220),
        ("satellite", "/v1/satellite", {"sat": {"latitude": 33.4484, "longitude": -112.074},
                                        "date_time": ONE_HOUR, "granularity": 100}, 14400),
        ("streetview", "/v1/streetview", {"latitude": 33.4484, "longitude": -112.074, "vertical_angle": 0,
                                          "horizontal_angle": 90, "back_view": False}, 8600),
        ("routing", "/v1/routing", {"origin": {"lat": 33.4484, "lon": -112.074},
                                    "destination": {"lat": 33.4255, "lon": -111.9400},
                                    "departure_time": "2025-07-15T14:00:00Z"}, 3500),
        ("heat_intelligence", "/v1/heat_intelligence", {"latitude": 33.4484, "longitude": -112.074,
                                                        "temperature": 40, "date": "2025-07-15",
                                                        "analysis": ["geographic", "environmental"]}, 8600),
    ]
    heatmap_id = None
    for name, path, body, documented in jobs:
        before, _ = credits()
        sub = record(f"{name}: submit", 200, call("POST", path, json_body=body, timeout=120))
        aid = ((sub.get("body") or {}).get("data") or {}).get("activity_id") if isinstance(sub.get("body"), dict) else None
        if not aid:
            continue
        done = poll(aid, max_s=900 if "intelligence" in name else 420)
        after, _ = credits()
        spent = (before - after) if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
        record(f"{name}: final status", "Completed", done,
               note=f"poll {done.get('poll_seconds')}s, statuses={done.get('statuses_seen')}, "
                    f"credits spent={spent} (documented {documented})")
        if name.startswith("heatmap") and heatmap_id is None:
            heatmap_id = aid
            record("heatmap: status with ?result_delivery=links", 200,
                   call("GET", f"/v1/status/{aid}", params={"result_delivery": "links"}))

    if heatmap_id:
        before, _ = credits()
        cr = record("monitors: create on our heatmap", 201, call("POST", "/v1/monitors", json_body={
            "heatmap_id": heatmap_id, "name": f"probe-{int(time.time())}", "boundary_geojson": BARE,
            "rules": [{"temporal_aggregation": "average", "spatial_aggregation": "maximum",
                       "operator": "above", "threshold": 45, "unit": "celsius"}],
            "notifications": {"email": ["probe@example.com"]}, "enabled": False, "generate_report": False}))
        mid = ((cr.get("body") or {}).get("data") or {}).get("monitor_id") if isinstance(cr.get("body"), dict) else None
        if mid:
            mid_credits, _ = credits()
            record("monitors: list", 200, call("GET", "/v1/monitors"))
            record("monitors: get", 200, call("GET", f"/v1/monitors/{mid}"))
            after_reads, _ = credits()
            record("monitors: patch", 200, call("PATCH", f"/v1/monitors/{mid}", json_body={"name": "probe-renamed"}))
            record("monitors: alerts", 200, call("GET", f"/v1/monitors/{mid}/alerts"))
            record("monitors: delete", 200, call("DELETE", f"/v1/monitors/{mid}"))
            after, _ = credits()
            try:
                note = (f"create cost={before - mid_credits}, list+get cost={mid_credits - after_reads}, "
                        f"total monitor flow cost={before - after} (docs imply 3,500 per call)")
            except TypeError:
                note = "could not read credits"
            results.append({"test": "monitor credit accounting", "note": note})
            print("      ", note)

save("api_probe.json", results)
print("\nSaved results/api_probe.json")
