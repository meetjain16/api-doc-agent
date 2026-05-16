---
name: doc_ingestor
description: Parse Go (Gin) or FastAPI source files to extract API endpoints, query parameters, request/response structs, and inline comments.
version: 1.0.0
---

# doc_ingestor

Statically analyses a local source tree and produces a structured `ingest.json`
payload consumed by `doc_generator` and `drift_detector`.

Supports two source types:

| Source type | Parser                     | Technique                          |
|-------------|----------------------------|------------------------------------|
| `go`        | `scripts/parser.py`        | Regex over Gin router patterns and Go struct tags |
| `fastapi`   | `scripts/fastapi_parser.py`| Python AST (`ast.walk`)            |

## Inputs

| Parameter       | Required | Default | Description                                     |
|-----------------|----------|---------|-------------------------------------------------|
| `--source-dir`  | No       | `sample_api_go` | Path to the local source tree to parse  |
| `--source-type` | No       | `go`    | One of `go` or `fastapi`                        |

## Usage

```bash
# Go service
python skills/doc_ingestor/scripts/main.py \
  --source-dir sample_api_go \
  --source-type go

# FastAPI service
python skills/doc_ingestor/scripts/main.py \
  --source-dir my_fastapi_service \
  --source-type fastapi
```

## Output

Writes `output/ingest.json` with the following structure:

```json
{
  "metadata": {
    "project": "API DocAgent",
    "source_repo": "<folder name>",
    "source_type": "go|fastapi",
    "generated_at": "<ISO-8601>",
    "total_endpoints": 87,
    "total_structs": 32
  },
  "endpoints": [
    {
      "path": "/api/v1/search",
      "method": "GET",
      "controller": "SearchController",
      "source_file": "handlers/search.go",
      "query_params": ["q", "page", "limit"],
      "request_structs": ["SearchRequest"],
      "comments": "...",
      "confidence": 1.0
    }
  ],
  "structs": [
    {
      "name": "SearchRequest",
      "fields": [
        { "name": "Query", "type": "string", "json": "q", "binding": "required" }
      ]
    }
  ]
}
```

## FastAPI parser details

- Two-pass: first collects all `BaseModel` subclasses across all files, then parses routes.
- Detects `APIRouter(prefix=...)` and prepends the prefix to route paths.
- Skips `Depends`/`Security` injected parameters (not query params).
- Handles both `def` and `async def` route functions.
- Ignores `test_*` files and common non-source directories (`venv`, `__pycache__`, `node_modules`, etc.).
- Filters using **relative** path parts to avoid false matches on absolute path components.

## Go parser details

- Extracts Gin router registrations: `router.GET(...)`, `router.POST(...)`, etc.
- Parses struct field tags: `json:"..."`, `form:"..."`, `binding:"..."`.
- Infers request/response struct associations from handler function signatures.
