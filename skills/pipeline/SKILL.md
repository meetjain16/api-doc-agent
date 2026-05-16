---
name: pipeline
description: Orchestrate the full API DocAgent pipeline — fetch → ingest → generate docs → drift detect — for one or more repos defined in repos.yaml.
version: 1.0.0
---

# pipeline

End-to-end runner that wires together `gitlab_reader`, `doc_ingestor`,
`doc_generator`, and `drift_detector` into a single command or programmatic call.

## Scripts

| File                   | Purpose                                             |
|------------------------|-----------------------------------------------------|
| `scripts/runner.py`    | Full pipeline runner and per-stage helper functions  |

## Configuration (`repos.yaml`)

```yaml
repos:
  - name: Product Search API
    project: indiamart/search/product-search-screen
    token: glpat-XXXXXXXXXXXX
    branch: main
    base_url: https://gitlab.indiamart.com
    source_type: fastapi          # go | fastapi
    description: Product search service
```

## Usage

### CLI

```bash
python skills/pipeline/scripts/runner.py --repo "Product Search API"
```

### Programmatic

```python
from skills.pipeline.scripts import runner

# Run full pipeline for a named repo
result = runner.run_by_name("Product Search API")
# result = { "status": "OK", "endpoints": 87, "docs_generated": 85, ... }

# Or call individual stages
repo_config = runner.get_repo_by_name("Product Search API")
file_count  = runner.fetch_repo(repo_config, target_dir)
ingest      = runner.run_ingest(target_dir, source_type="fastapi")
```

## Pipeline stages

```
repos.yaml
    │
    ▼
1. fetch_repo()      GitLab API → local src/
    │
    ▼
2. run_ingest()      parser → ingest.json
    │
    ▼
3. generate_docs()   LLM per endpoint → generated_docs.json / .md
    │
    ▼
4. drift_detection() comparator → breaking_changes.json / .md
```

## Output layout

```
output/repos/{slug}/
├── src/                    # downloaded source files
├── ingest.json             # stage 2 output
├── generated_docs.json     # stage 3 output
├── generated_docs.md       # stage 3 output (Markdown)
├── breaking_changes.json   # stage 4 output
└── breaking_changes.md     # stage 4 output (Markdown)
```

## Notes

- Each repo gets its own output directory keyed by a URL-safe slug of its name.
- The FastAPI parser is always reloaded on each run (`force_reload=True`) so code
  changes to the parser take effect without restarting the server.
- Drift detection is best-effort: a failure does not abort the pipeline.
