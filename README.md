# FortyGuard Product Evaluation: Dashboard, Temperature API® & MCP

A product review of the FortyGuard Temperature Dashboard®, the
[Temperature API®](https://docs-api.fortyguard.com/docs/introduction) and the Temperature MCP. It is based on tests against the live services (November 2026), not only on reading the docs.

**Start with [FINDINGS.md](FINDINGS.md)**: it has the ratings, the issues found and the suggested fixes.

## What's in here

| File | What it does |
|---|---|
| `FINDINGS.md` | The written review: answers, evidence, and a prioritized fix list |
| `01_docs_audit.py` | Renders every docs page with headless Chrome and runs automatic consistency checks |
| `02_api_probe.py` | Calls the REST API: auth, validation and error handling (free), then every endpoint for real (`--paid`), comparing the credits actually charged with the documented cost |
| `03_mcp_probe.py` | A minimal MCP client (raw JSON-RPC, no SDK): handshake, tool discovery, schema dump, bad-input handling, then real tool calls (`--paid`) |
| `04_monitor_flow.py` | Monitor lifecycle (create → list → get → patch → alerts → delete), with the credits charged at each step |
| `fg_common.py` | Shared helpers. The API key is loaded from `.env` and redacted from every saved file |
| `results/` | Raw output from the runs (`api_probe.json`, `mcp_probe.json`, `mcp_tools.json`, `docs_audit.md`) |
| `docs_snapshot/` | Text snapshot of the docs as reviewed |

## Run it yourself

```bash
pip install requests 
python 01_docs_audit.py                      # needs Chrome or Edge installed
python 02_api_probe.py                       # free checks only
python 03_mcp_probe.py                       # free checks only
python 02_api_probe.py --paid                # uses about 70k credits
python 03_mcp_probe.py --paid                # uses about 40k credits
```