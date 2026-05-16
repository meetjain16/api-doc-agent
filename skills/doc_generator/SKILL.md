---
name: doc_generator
description: Generate structured AI documentation for each API endpoint using an LLM, with deterministic fallbacks when AI is unavailable.
version: 1.0.0
---

# doc_generator

Reads the `ingest.json` produced by `doc_ingestor`, calls an LLM for each endpoint,
and writes `generated_docs.json` + `generated_docs.md`.

## Scripts

| File                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `scripts/main.py`       | Orchestrator — enriches endpoints, calls LLM, writes output |
| `scripts/openai_client.py` | OpenAI-compatible LLM client (supports org proxies)   |
| `scripts/prompts.py`    | Prompt builder — assembles per-endpoint context          |

## LLM configuration (`.env`)

```dotenv
LLM_BASE_URL=https://imllm.intermesh.net/v1   # Org proxy endpoint
LLM_API_KEY=sk-...                             # Org API key
LLM_MODEL=anthropic/claude-haiku-4-5           # Model identifier
```

The client uses the **OpenAI-compatible** API (`/chat/completions`) so any OpenAI-spec
proxy (LiteLLM, OpenRouter, internal gateways) works by changing `LLM_BASE_URL`.

## Usage

```bash
python skills/doc_generator/scripts/main.py
```

Reads from `output/ingest.json`, writes to `output/generated_docs.json` and `output/generated_docs.md`.

## Output schema (`generated_docs.json`)

```json
{
  "metadata": { "generated_endpoints": 87, "skipped_endpoints": 2, ... },
  "endpoints": [
    {
      "path": "/api/v1/search",
      "method": "GET",
      "ai_sections": {
        "generation_status": "ai | fallback",
        "endpoint_summary": "...",
        "business_summary": "...",
        "request_explanation": "...",
        "response_explanation": "...",
        "validation_notes": ["..."],
        "sample_curl": "curl -X GET ...",
        "edge_cases": ["..."],
        "openapi_schema_summary": "..."
      }
    }
  ]
}
```

## Fallback behaviour

When the LLM call fails or returns invalid JSON, the skill generates deterministic fallback content:
- `sample_curl` is built from the endpoint path, method, and extracted query params.
- `validation_notes` lists required fields from struct binding tags.
- `generation_status` is set to `"fallback"` so the dashboard can highlight these.

## Progress callback

`generate_docs(ingest, progress_callback=None)` accepts an optional callable
`progress_callback(current, total, path)` called after each endpoint — used by the
Streamlit dashboard to render a live progress bar.
