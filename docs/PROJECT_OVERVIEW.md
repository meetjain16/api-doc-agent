# API DocAgent — Project Overview

## What is API DocAgent?

API DocAgent is an AI-powered API intelligence platform that automatically reads your service's source code, generates human-readable documentation for every endpoint, and continuously monitors whether your existing documentation has drifted out of sync with reality.

Most engineering teams face the same problem: APIs change frequently, but documentation updates lag behind — or never happen. API DocAgent closes that gap by making documentation a byproduct of the code itself, not a manual task.

---

## Key Features

### 1. Automatic Route Discovery

API DocAgent parses your source code directly — no annotations, no decorators, no YAML files required upfront.

**For Go (Gin framework):**
- Finds every `router.GET(...)`, `router.POST(...)`, `router.PUT(...)`, etc.
- Extracts the handler function name (controller)
- Reads Go struct tags (`json:"..."`, `form:"..."`, `binding:"required"`) to discover request and response shapes

**For Python (FastAPI):**
- Uses Python's AST (Abstract Syntax Tree) parser — reads code structure without executing it
- Detects `@app.get(...)`, `@router.post(...)`, and all HTTP method decorators
- Automatically handles `APIRouter(prefix="/v1")` — prefixes are applied to all child routes
- Collects every `BaseModel` subclass (Pydantic models) and links them to the routes that use them
- Skips dependency-injected parameters (`Depends`, `Security`) — these are framework internals, not API parameters

Each discovered endpoint gets a **confidence score**:
- `1.0` — has a route path, method, controller, inline comments, and query params
- `0.7` — has route and method but limited metadata
- `0.5` — partial information only

---

### 2. AI Documentation Generation

Once endpoints are extracted, API DocAgent sends each one to an LLM (via your org's proxy at `imllm.intermesh.net`) and asks it to produce structured documentation.

For every endpoint, the AI generates:

| Section | What it contains |
|---|---|
| **Endpoint Summary** | A concise technical description of what the route does |
| **Business Context** | Why this endpoint exists — the business workflow it serves |
| **Request Explanation** | What fields to send, what they mean, and when they're required |
| **Response Explanation** | What the response shape looks like and what each field means |
| **Validation Notes** | Required fields, format constraints, binding rules |
| **Edge Cases** | Known failure modes, empty state handling, boundary conditions |
| **Sample curl** | A ready-to-run curl command with real example values |
| **OpenAPI Schema Summary** | A compact schema note describing method, path, params, and models |

**Fallback mode:** If the LLM is unavailable or the key is missing, API DocAgent still produces useful documentation deterministically — building the curl from the extracted path and params, listing required fields from struct binding tags, and marking the status as `fallback` so you know where to improve.

---

### 3. Drift Detection

Drift is the gap between what your code does and what your documentation says it does.

It happens naturally over time:
- A field gets renamed (`user_id` → `userId`) but the docs still say `user_id`
- A new required parameter is added but never documented
- An old endpoint is removed but its documentation page still exists
- A response field is deprecated in code but the consumer-facing docs still describe it

**API DocAgent detects drift in two modes:**

#### Mode A — Stale Docs Comparison
If you have existing Markdown documentation (e.g. a wiki export, a Confluence page, or a `stale_docs.md` file), the drift detector compares it field-by-field against what the source code actually contains.

It finds:

| Issue Type | Severity | What it means |
|---|---|---|
| `REMOVED_FIELD` | HIGH | A field your docs describe no longer exists in the code |
| `POSSIBLE_RENAMED_FIELD` | HIGH | A field looks like it was renamed (fuzzy similarity match ≥ 72%) |
| `RESPONSE_MISMATCH` | HIGH | Documented response shape differs from the generated schema |
| `UNDOCUMENTED_RESPONSE_FIELD` | MEDIUM | A field exists in code but is never mentioned in docs |
| `UNDOCUMENTED_QUERY_OR_REQUEST_FIELD` | MEDIUM | A query param or request field exists in code with no docs |
| `DEPRECATED_FIELD` | MEDIUM | A field is marked deprecated in code but still in the docs |

#### Mode B — Self-Analysis (no stale docs needed)
When no existing documentation exists, the drift detector analyses the AI-generated output itself:
- Flags every endpoint where AI generation failed (`generation_status: fallback`)
- Lists every undocumented query parameter found in source
- Highlights endpoints with no request or response schema resolved

This mode gives you a **documentation health score** for a brand-new service — useful at the start of a project to know what coverage gaps exist.

---

### 4. Multi-Repo Support

API DocAgent supports multiple repositories configured in a single `repos.yaml` file. Each repo is fetched, parsed, documented, and drift-checked independently — with output stored in its own directory (`output/repos/{slug}/`).

```yaml
repos:
  - name: Product Search API
    project: indiamart/search/product-search-screen
    token: glpat-XXXX
    branch: main
    base_url: https://gitlab.indiamart.com
    source_type: fastapi
```

No git binary is needed — files are fetched directly via the GitLab API v4.

---

### 5. Interactive Dashboard

The Streamlit dashboard provides a browser-based interface over all generated artifacts.

**Overview Dashboard** — health metrics at a glance: total APIs, structs extracted, AI docs generated, drift issues found, high-severity count.

**API Explorer** — searchable, filterable table of all discovered endpoints. Filter by HTTP method, search by path, controller name, or query param. Download the full list as CSV.

**Generated Documentation Viewer** — browse every endpoint's AI-generated documentation across four tabs:
- *Overview* — summary, business context, request and response explanations
- *Parameters & Fields* — query params, path params, request and response structs
- *Request / Response* — full field tables with types and binding rules
- *Developer Tools* — sample curl, per-endpoint JSON and Markdown download

**Drift Detection Dashboard** — categorised drift findings grouped by removed fields, renamed fields, and undocumented fields. Includes PR-style engineering alerts formatted for copy-paste into GitHub or GitLab comments.

---

## How It All Connects

```
repos.yaml
    │
    ▼
GitLab API ──► Source files (.py / .go)
                    │
                    ▼
            doc_ingestor  ──► ingest.json
            (AST / regex)      (endpoints + structs)
                    │
                    ▼
            doc_generator ──► generated_docs.json
            (LLM per endpoint)  generated_docs.md
                    │
                    ▼
            drift_detector ──► breaking_changes.json
            (compare / self-analyse)  breaking_changes.md
                    │
                    ▼
            Streamlit Dashboard
            (explore · download · act)
```

---

## Output Artifacts

| File | Contents | Use |
|---|---|---|
| `ingest.json` | All discovered endpoints and structs | Input to doc generator and drift detector |
| `generated_docs.json` | Structured AI documentation per endpoint | Consumed by dashboard and drift detector |
| `generated_docs.md` | Full Markdown documentation | Ready to paste into Confluence, Notion, or GitHub wiki |
| `breaking_changes.json` | Drift issues structured by endpoint and severity | CI/CD integration, alerting |
| `breaking_changes.md` | Human-readable drift report with PR-style alerts | Share with teams, post in PRs |

---

## Why This Matters

| Without API DocAgent | With API DocAgent |
|---|---|
| Documentation written manually, months after code ships | Documentation generated in seconds from the source |
| No one knows which endpoints are undocumented | Every undocumented endpoint is surfaced automatically |
| Field renames break consumers silently | Renamed fields are caught before release |
| Docs rot as code evolves | Drift is detected on every pipeline run |
| Onboarding requires reading source code | New engineers browse a live, searchable API catalogue |
