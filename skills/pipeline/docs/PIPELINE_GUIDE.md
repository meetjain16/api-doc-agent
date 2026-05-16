# API DocAgent — Pipeline Guide

## Terminology

| Term | Definition |
|------|------------|
| **Skill** | A self-contained folder (`SKILL.md` + `scripts/`) that performs one pipeline stage |
| **Ingest** | Parsing source code (Go/FastAPI) to extract endpoints, structs, and params |
| **Endpoint** | One HTTP route (`METHOD /path`) discovered in the source tree |
| **Struct** | A request or response data model (Go struct or Pydantic `BaseModel`) |
| **Confidence** | A score (0.5–1.0) assigned by the ingestor based on how complete an endpoint's metadata is |
| **AI Sections** | The LLM-generated documentation fields for one endpoint (summary, business context, curl, etc.) |
| **Generation Status** | `ai` — LLM generated docs; `fallback` — deterministic fallback used (no LLM or LLM failed) |
| **Stale Docs** | Pre-existing human-written Markdown documentation used as the drift baseline |
| **Drift** | A mismatch between what the source code says and what existing documentation says |
| **Self-Analysis Mode** | Drift detection without stale docs — flags AI failures and undocumented fields from the generated docs alone |
| **Slug** | URL-safe repo identifier derived from the repo name (e.g. `Product Search API` → `product-search-api`) |
| **LLM Proxy** | An OpenAI-compatible gateway (e.g. `imllm.intermesh.net`) that routes requests to models like Claude |

---

## Uses

### 1. Auto-document a new service
Run the full pipeline against any Go or FastAPI repo to instantly generate structured API docs — no manual writing required.

### 2. Catch undocumented endpoints
The ingestor finds every registered route in the codebase, including ones that were never added to any wiki or Confluence page.

### 3. Detect doc drift before a release
Point the drift detector at your existing Markdown docs to find removed fields, renamed parameters, or endpoints that have changed shape since the docs were last updated.

### 4. Generate curl examples automatically
Even in fallback mode (no LLM), the pipeline builds a valid `curl` command for every endpoint using the extracted path, method, and query params.

### 5. Export for downstream tooling
Every stage writes JSON — ingest.json, generated_docs.json, breaking_changes.json — so the output can be consumed by CI/CD pipelines, Slack bots, or internal portals.

---

## Phase-wise Changes (Changelog)

### Phase 1 — Initial scaffold
- Go/Gin parser (`doc_ingestor/scripts/parser.py`) with regex-based route and struct extraction
- Basic OpenAI doc generator — one LLM call per endpoint
- Sample stale docs drift detector
- Streamlit dashboard (single repo, hardcoded paths)

### Phase 2 — FastAPI support
- Added Python AST parser (`doc_ingestor/scripts/fastapi_parser.py`)
- Two-pass model collection: global `BaseModel` registry before route parsing
- `APIRouter(prefix=...)` detection for route prefix propagation
- `Depends`/`Security` parameter filtering (not treated as query params)
- `async def` route function support
- Fixed `scan_python_files` to use **relative** path parts — prevents false exclusions when the absolute path contains a word like `output`

### Phase 3 — GitLab integration & multi-repo
- GitLab API v4 fetcher (`gitlab_reader/scripts/main.py`) — no `git` binary required
- `repos.yaml` config for declaring multiple repos with tokens and source types
- Per-repo output directories: `output/repos/{slug}/`
- Pipeline runner (`pipeline/scripts/runner.py`) wiring all stages into one call
- Multi-repo sidebar dropdown in the Streamlit dashboard

### Phase 4 — LLM switch & UI overhaul
- Replaced OpenAI SDK with OpenAI-compatible client pointed at org proxy (`imllm.intermesh.net`)
- Config via `.env`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Fast-fail on auth errors (no retries on 401)
- Complete Streamlit dark theme (GitHub-style: `#0d1117` background)
- Method badges (GET=green, POST=blue, PUT=yellow, DELETE=red, PATCH=purple)
- 4-tab endpoint viewer: Overview · Parameters & Fields · Request/Response · Developer Tools
- Download buttons: JSON, Markdown, CSV for every artifact

### Phase 5 — Pipeline progress UI & skill restructure
- Live pipeline progress: `st.status` panel with stage-by-stage updates
- Per-endpoint AI generation counter (`Documented X / Y`) with last-path label
- Progress callback in `generate_docs(ingest, progress_callback=None)`
- Streamlit banner/toolbar hidden via CSS
- **Skill restructure**: every skill now follows the standard layout:
  ```
  skill_name/
  ├── SKILL.md        ← metadata + instructions
  └── scripts/        ← executable code
  ```
- `pipeline/scripts/runner.py` updated: `parents[3]` for new depth, `scripts/` paths for all modules
- Drift detector **self-analysis mode**: runs without stale docs — flags AI fallbacks, undocumented query params, and missing schemas from `generated_docs.json` directly
