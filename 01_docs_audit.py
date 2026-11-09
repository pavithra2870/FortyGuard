"""Snapshot the FortyGuard docs and run automatic consistency checks.

The docs site is an Angular single-page app (plain curl gets an empty shell, and there is
no llms.txt / sitemap / OpenAPI file), so we render each page with headless Chrome.

  python 01_docs_audit.py      -> writes docs_snapshot/*.txt and results/docs_audit.md
"""
import html
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "docs_snapshot"
SNAP.mkdir(exist_ok=True)
BASE = "https://docs-api.fortyguard.com"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
]
CHROME = next(c for c in CHROME_CANDIDATES if c and Path(c).exists())


def slugs():
    """Find every /docs/<slug> route inside the JS bundle."""
    shell = requests.get(f"{BASE}/docs/introduction", timeout=30).text
    main = re.search(r'src="(main\.[0-9a-f]+\.js)"', shell).group(1)
    js = requests.get(f"{BASE}/{main}", timeout=60).text
    return sorted(set(re.findall(r'"/docs/([a-z0-9-]+)"', js) + re.findall(r'id:"([a-z]+(?:-[a-z]+)*)"', js))
                  - {"section-optional", "section-required", "section-result-schema", "section-output-fields"})


def render(slug):
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000",
                          "--dump-dom", f"{BASE}/docs/{slug}"], capture_output=True, timeout=90)
    s = out.stdout.decode("utf-8", "ignore")
    m = re.search(r"<main.*?</main>", s, flags=re.S)
    s = m.group(0) if m else s
    s = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", "", s, flags=re.S)
    s = re.sub(r"<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + re.sub(r"<[^>]+>", "", m.group(1)) + "\n```\n",
               s, flags=re.S)
    s = re.sub(r"</(td|th)>", " | ", s)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    t = "\n".join(line.rstrip() for line in t.splitlines() if line.strip())
    i = t.find("Release Notes\n")  # drop the sidebar
    t = t[i + 14:] if i >= 0 else t
    (SNAP / f"{slug}.txt").write_text(t, encoding="utf-8")
    return slug, t


def main():
    pages = dict(ThreadPoolExecutor(6).map(render, slugs()))
    allt = "\n".join(pages.values())
    findings = []

    def check(ok, msg):
        if not ok:
            findings.append(msg)

    # 1. machine-readable docs
    for f in ("llms.txt", "openapi.json", "sitemap.xml"):
        r = requests.get(f"{BASE}/{f}", timeout=20)
        check(r.ok and "<app-root>" not in r.text, f"No `{f}` (request returns the SPA HTML shell).")
    # 2. empty / thin pages
    for slug, t in pages.items():
        check(len(t) > 400, f"Page `/docs/{slug}` is (nearly) empty: {len(t)} chars.")
    # 3. contradictions we know to look for
    hi = pages.get("heat-intelligence", "")
    check(not ("Fahrenheit" in hi and "Celsius" in hi),
          "Heat Intelligence: `temperature` described as Fahrenheit AND 'the supplied Celsius temperature'.")
    check("six POST endpoints" not in allt, "Quickstart says 'six POST endpoints' but 7 POST endpoints are documented.")
    check(not ("2019-01-01" in allt and "2021-01-01" not in allt),
          "REST docs say data starts 2019-01-01; MCP server's coverage resource says 2021-01-01.")
    mon = [s for s in pages if s.startswith("monitoring-")]
    paid_reads = [s for s in mon if "3,500 credits per request" in pages[s] and s in
                  ("monitoring-list", "monitoring-get", "monitoring-alerts", "monitoring-delete")]
    check(not paid_reads, f"Every Monitor endpoint (incl. read-only {paid_reads}) says '3,500 credits per request'; "
                          "the MCP server says list operations are free and our test spent 0 credits.")
    rep = pages.get("monitoring-report", "")
    check(not ("?type=pdf" in rep and "file_type" in rep), "Alert report download: prose says `?type=pdf`, code uses `file_type`.")
    check("rate limit" in pages.get("limitations", "").lower().replace("rate limit exceeded", ""),
          "Release notes promise rate limits on Known Limitations, but no rate-limit numbers exist anywhere (429 is listed).")
    rn = pages.get("release-notes", "")
    for feat in ("routing", "monitor", "MCP", "20 m", "Startup"):
        check(feat.lower() in rn.lower(), f"Release notes (only v1.0.0) never mention `{feat}`, which the docs now describe.")
    hm = pages.get("create-heatmap", "")
    check(not ("FeatureCollection" in pages.get("quickstart", "") and "'type': 'Polygon'" in hm),
          "`polygon_aoi` is a FeatureCollection in Quickstart but a bare Polygon in the Create Heatmap example.")
    check("orignal_image" not in allt.lower(), "Satellite result uses misspelled `orignal_image` (legacy alias kept).")
    check("/v1/alerts/{alert_id}" not in pages.get("monitoring-alerts", ""),
          "`GET /v1/alerts/{alert_id}` is mentioned but has no page (and returns 422 in our test).")

    report = ["# Docs audit (automatic checks)", "", f"Pages rendered: {len(pages)}", ""]
    report += [f"- {f}" for f in findings]
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "docs_audit.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
