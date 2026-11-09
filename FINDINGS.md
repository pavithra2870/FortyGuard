# FortyGuard Evaluation: Temperature API®, MCP and Dashboard

**Evaluator:** Pavithra K R · **Date:** Nov 2026 · **Account:** intern trial (Premium, 1M credits)

Hands-on testing: 60+ live requests to the API and MCP server, with the credits charged checked against the documented prices.

## Top issues
1. **Heat Intelligence temperature unit is unclear.** The docs say °F and °C on the same page; the MCP schema says °F. I sent `40` (°C) and got a Phoenix July report at **4.44 °C**, with no warning.
2. **Four invalid inputs return 500** instead of 400: bad date format, a range over 31 days, routing origin = destination, a route over 200 km.
3. **Docs don't match the live system.** 11 MCP tools vs 9 documented; `wait_for_completion` doesn't exist; Monitor calls are documented at 3,500 credits but cost 0; the Create Monitor example fails with 422.
4. **Five different error formats**, and 400 and 422 are mixed for the same kind of error.
5. **Nothing machine-readable:** no OpenAPI, no `llms.txt`, no rate limits, and a JavaScript-only docs site.

## API: what works
- One async pattern: submit → `activity_id` → `GET /v1/status/{id}`.
- Credits charged exactly as documented; failed and rejected requests are free.
- Clear validation on newer paths (`OUT_OF_COVERAGE`, unclosed polygon), `?result_delivery=links`, and structured routing errors.

## Measured results (downtown Phoenix)
| Endpoint | Time | Size | Credits | Docs |
|---|---|---|---|---|
| env_params | 9 s | 3.5 KB | 2,900 | ✅ |
| heatmap (0.35 mi², 100 m) | 24 s | 32 KB | 4,220 | ✅ |
| satellite | 15 s | 576 KB | 14,400 | ✅ |
| streetview | 13 s | 540 KB | 8,600 | ✅ |
| routing | 17 s | 12 KB | 0 in cycle / 3,500 in total | ⚠️ |
| heat_intelligence | 238 s | 18-page PDF | 8,600 | ✅ |
| monitors (6 operations) | ~2 s | small | 0 each | ⚠️ docs say 3,500 |

## API design issues
- Heat Intelligence makes the caller supply the temperature, even though FortyGuard is the temperature source. Make it optional, or name the unit explicitly (`temperature_c`).
- The credits endpoint takes the key in the JSON body. Add `GET /v1/credits` that uses the header.
- Billing counters disagree (42,940 vs 46,440): routing is missing from the cycle total and the activity breakdown.
- The satellite image is sent twice (`original_image` and the typo `orignal_image`).
- Monitors reject the bare Polygon that heatmap accepts.
- No idempotency key on REST (MCP has one), so a retry can charge twice.
- Polling only; no webhooks.
- About 1–2 s baseline latency, even on a 401.

**Missing endpoints:** list my activities, cancel a job, dry-run cost estimate, coverage check, point temperature lookup, batch requests, `GET /v1/credits`. `GET /v1/alerts/{id}` is documented but returns 422.

## Error handling
22 bad inputs tested; all were rejected at no cost, but:

| Input | Expected | Got |
|---|---|---|
| `start_date: "07/15/2024"` | 400 | **500** |
| 61-day range (limit 31) | 400 | **500** |
| routing origin = destination | 400 | **500** |
| route > 200 km | 400 | **500** |
| unclosed polygon / outside US | 400 | 400 ✅ clear message |
| granularity 50, latitude 999 | 400 (per docs) | 422, good message |

The error formats seen: `details.message`, `message + field + detail[]`, `message + code`, a body with no `status_code`, `{"detail":...}`, and plain text.
**Fix:** use one schema, `{error:{code, message, field, retryable}, request_id}`, everywhere. The MCP server already does this.

## Documentation
**Good:** runnable quickstart, cost and plan shown on every page, honest coverage notes, Known Limitations page, QGIS guide.

**Problems:**
- **Broken examples:** the Create Monitor example; Polygon vs FeatureCollection; the quickstart poller checks for statuses that don't exist; fake IDs (`heatmap_abc123`).
- **Empty or missing:** the Error Handling page, rate limits, a reference page for the credits API, the `start_time` timezone, field types, the Street View `back` output.
- **Not machine-readable:** no OpenAPI, `llms.txt` or sitemap.

**Improve:** generate the docs from an OpenAPI spec, fill the Errors page, add `llms.txt` and pre-rendering, test the examples in CI, keep a changelog, add PowerShell snippets and a "which endpoint" guide.

## MCP
**Tried:** every tool (`env_params`, `heatmap`/`heatmap_read`, `satellite`, `streetview`, `temperature_routing`/`_read`, `report`/`report_read`, `credit_balance`), using a raw JSON-RPC client I wrote and [AI client].

**Good:**
- Connected on the first try.
- Paid tools ask the user to confirm the cost first.
- Read-only and destructive hints on tools.
- Structured errors with `trace_id`.
- Imagery trimmed to about 2 KB (vs 576 KB over REST).
- Useful resources (coverage, units, entitlements).

**Issues:**
- 11 tools live vs 9 documented. The undocumented `monitoring` tool bundles 14 operations, including `delete_heatmap_data`, so one permission covers both read and delete.
- `wait_for_completion` is documented but silently ignored.
- `report.temperature`: °C in the docs, °F in the schema.
- The tool list is about 8.5K tokens, loaded into the AI's context every turn.
- Errors are vague ("input is invalid" plus a field name only).
- A 401 points to OAuth on a `dev-` Auth0 tenant, which conflicts with the docs' simple Bearer key.
- No 20 m resolution; three different ID names across the read tools.
- Setup is bash-only, and the Claude Code command stores the key in plain text.

## Data quality
- Street View in downtown Phoenix returned an **indoor 2015 photo** (sofa, ceiling, cabinet), with no warning.
- Satellite segmentation returns `sky` and `skyscraper` classes, which suggests a street-level model used on aerial images.
- The heatmap spread was only ±0.03 °C across a 1 km² downtown area. Worth confirming this is expected.

## Scalability
**Risks:**
- No shared spec across the REST docs, MCP docs and servers, so they drift.
- Polling-only load.
- No published rate limits.
- Mismatched billing counters.

**Fix:** use OpenAPI as the single source for docs, SDKs and MCP schemas; add versioning and deprecation headers, webhooks, and `X-RateLimit-*` headers.

## Priorities
| P | Fix |
|---|---|
| P0 | Heat Intelligence unit; the four 500s; wrong docs (Monitor example, prices, tool count, `wait_for_completion`) |
| P1 | One error schema and the Errors page; OpenAPI and `llms.txt`; fix billing counters and `GET /v1/credits` |
| P2 | Activity list, dry run, coverage check, webhooks; Street View filtering; slimmer MCP catalog; split the `monitoring` tool |
