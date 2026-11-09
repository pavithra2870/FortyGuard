"""Monitor lifecycle test (create -> list -> get -> patch -> alerts -> delete) with credit accounting.
Usage: python 04_monitor_flow.py <heatmap_activity_id>
Note: the docs example sends boundary_geojson as a bare Polygon, which the API rejects (422);
it actually requires a FeatureCollection."""
import sys, time
from fg_common import call, key, save, shrink

hid = sys.argv[1]
PHX = [[-112.0790, 33.4440], [-112.0690, 33.4440], [-112.0690, 33.4530], [-112.0790, 33.4530], [-112.0790, 33.4440]]
FC = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
      "geometry": {"type": "Polygon", "coordinates": [PHX]}}]}
def credits():
    b = call("POST", "/v1/system/fetch-api-key-usage", json_body={"api_key": key()})["body"]
    return b["credit_summary"]["cycle_remaining_credits"]
out = []
def step(name, res):
    c = credits(); spent = step.prev - c; step.prev = c
    print(f"{res['status']:>4} {res['ms']:>6}ms  credits spent={spent:>5}  {name}")
    out.append({"step": name, "status": res["status"], "credits_spent": spent, "body": shrink(res["body"])})
    return res
step.prev = credits()
r = step("create (FeatureCollection boundary)", call("POST", "/v1/monitors", json_body={
    "heatmap_id": hid, "name": f"probe-{int(time.time())}", "boundary_geojson": FC,
    "rules": [{"temporal_aggregation": "average", "spatial_aggregation": "maximum", "operator": "above",
               "threshold": 45, "unit": "celsius"}],
    "notifications": {"email": ["probe@example.com"]}, "enabled": False, "generate_report": False}))
mid = (r["body"].get("data") or {}).get("monitor_id") if isinstance(r["body"], dict) else None
if mid:
    step("list", call("GET", "/v1/monitors"))
    step("get", call("GET", f"/v1/monitors/{mid}"))
    step("patch (rename)", call("PATCH", f"/v1/monitors/{mid}", json_body={"name": "probe-renamed"}))
    step("list alerts", call("GET", f"/v1/monitors/{mid}/alerts"))
    step("delete", call("DELETE", f"/v1/monitors/{mid}"))
    step("get after delete", call("GET", f"/v1/monitors/{mid}"))
save("monitor_flow.json", out)
