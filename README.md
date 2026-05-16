# API DocAgent

API DocAgent is a hackathon prototype for API intelligence on Go services. It
parses a layered Go REST codebase, extracts API metadata, generates AI-assisted
documentation, detects schema drift against stale docs, and presents everything
in a Streamlit dashboard.

The project is intentionally lightweight and demo-focused. It avoids production
integrations such as databases, Redis, RabbitMQ, tracing, and external APIs.

## What We Built

```text
api-doc-agent/
├── sample_api_go/                 # Small runnable Go demo service
├── skills/
│   ├── doc_ingestor/              # Go route/schema parser
│   ├── doc_generator/             # OpenAI-powered documentation generator
│   └── drift_detector/            # Schema drift comparator and reports
├── streamlit_app/                 # Hackathon dashboard
├── output/                        # Generated ingestion/docs/drift artifacts
├── requirements.txt
└── README.md
```

Core capabilities:

- API route discovery from Go router/controller files
- Request and response schema extraction from Go structs
- AI-generated API documentation
- Drift detection against intentionally stale Markdown docs
- Breaking-change reports for engineering review
- Streamlit dashboard for demo presentation

## Demo APIs

The bundled Go service in `sample_api_go/` includes realistic business APIs for:

- GST search
- GST user details
- company profile details
- meeting screen checks
- video meeting data
- onboarding/company listing

These APIs include query params, nested structs, deprecated fields, stale
comments, and mismatched old docs so the full API DocAgent workflow can be
demonstrated end to end.

## Setup

From the repository root:

```bash
cd /home/imart/Desktop/Hackathon/10xproductivity/api-doc-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Optional, but recommended for AI-generated documentation:

```bash
cat > .env <<'EOF'
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
EOF
```

If `OPENAI_API_KEY` is missing, the doc generator still produces fallback
documentation from extracted metadata, but AI summaries will be limited.

## Run the Go Demo Service

```bash
cd /home/imart/Desktop/Hackathon/10xproductivity/api-doc-agent/sample_api_go
go run .
```

Default port: `8088`

Example:

```bash
curl "http://localhost:8088/go/api/nsd/v1/fsa/GstSearch?empid=98123&AK=demo&gst=07AAECS1234F1Z5&source=mobile_app"
```

## Generate API Intelligence Artifacts

Run these commands from the project root:

```bash
cd /home/imart/Desktop/Hackathon/10xproductivity/api-doc-agent
source venv/bin/activate
```

### GitLab API import mode

If you have a read-only GitLab token, you can import a repo directly without
cloning it first:

```bash
python skills/gitlab_reader/main.py \
   --base-url https://gitlab.com \
   --project your-group/your-service \
   --branch main \
   --token <read-token> \
   --target-dir sample_api_go
```

Then run the normal pipeline steps against the imported folder.

### 1. Ingest Go API Metadata

```bash
python skills/doc_ingestor/main.py
```

Creates:

- `output/ingest.json`

This contains parsed endpoints, HTTP methods, controllers, comments, query
params, structs, fields, and confidence scores.

### 2. Generate API Documentation

```bash
python skills/doc_generator/main.py
```

Creates:

- `output/generated_docs.json`
- `output/generated_docs.md`

The JSON output is machine-readable and useful for future automation. The
Markdown output is human-readable API documentation.

### 3. Detect Schema Drift

```bash
python skills/drift_detector/main.py
```

Compares:

- `output/generated_docs.json`
- `sample_api_go/docs/stale_docs.md`

Creates:

- `output/breaking_changes.json`
- `output/breaking_changes.md`

The drift detector reports removed fields, likely renamed fields, undocumented
fields, response mismatches, deprecated fields, and missing endpoint docs.

## Launch the Dashboard

```bash
cd /home/imart/Desktop/Hackathon/10xproductivity/api-doc-agent
source venv/bin/activate
streamlit run streamlit_app/app.py
```

The dashboard includes built-in pipeline controls in the sidebar, so you can
run Step 1, Step 2, Step 3, or the full pipeline without leaving the app.

Dashboard sections:

- Overview Dashboard: parsed API counts, struct counts, drift counts
- API Explorer: searchable endpoint table and confidence scores
- Generated Documentation Viewer: request fields, response fields, query params,
  validation notes, edge cases, and generated Markdown
- Drift Detection Dashboard: high severity alerts, renamed/removed/undocumented
  fields, PR-style engineering alerts, and Markdown drift report

## Output Files

| File | Purpose |
| --- | --- |
| `output/ingest.json` | Raw parser output from the Go demo service |
| `output/generated_docs.json` | Structured generated API documentation |
| `output/generated_docs.md` | Human-readable generated API docs |
| `output/breaking_changes.json` | Structured drift and breaking-change results |
| `output/breaking_changes.md` | PR-style drift report for engineering review |

## How the Pipeline Works

1. `doc_ingestor` scans `sample_api_go/` using regex and string parsing.
2. It extracts routes, methods, controller names, comments, query params, and Go
   struct fields.
3. `doc_generator` enriches endpoints with request/response fields and sends
   source-grounded prompts to the OpenAI wrapper.
4. `drift_detector` compares generated schemas against stale Markdown docs.
5. `streamlit_app` presents the full API intelligence workflow in a polished
   dashboard.

## Supported Source Types

The ingestor now auto-detects the project type:

- Go services using Gin-style routing and Go structs
- FastAPI services using route decorators and Pydantic models

If a repo contains only Python sources, the FastAPI parser is used.

## Notes for Hackathon Judges

This prototype is optimized for clarity and demo value:

- The Go service is intentionally small and self-contained.
- The parser is lightweight and explainable.
- Stale docs are intentionally wrong to demonstrate drift detection.
- The dashboard shows both machine-readable and human-readable outputs.
- The drift report can be reused later for CI or PR review automation.

## Common Troubleshooting

If Streamlit cannot find generated files, run the pipeline first:

```bash
python skills/doc_ingestor/main.py
python skills/doc_generator/main.py
python skills/drift_detector/main.py
```

If OpenAI calls fail, check:

- `.env` exists at the repo root
- `OPENAI_API_KEY` is set
- dependencies were installed with `pip install -r requirements.txt`

If the Go demo service does not start, check:

- Go is installed
- port `8088` is available
- run from `sample_api_go/`
