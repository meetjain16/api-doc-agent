---
name: gitlab_reader
description: Fetch source files from a GitLab repository via the GitLab API v4 using a private token — no git binary required.
version: 1.0.0
---

# gitlab_reader

Downloads selected source files (`.py`, `.go`, `.md`) from a GitLab repository
using the GitLab REST API v4. Useful when only a read-access private token is available
and `git clone` is not an option (e.g. CI environments, air-gapped networks).

## Inputs

| Parameter        | Required | Default              | Description                                      |
|------------------|----------|----------------------|--------------------------------------------------|
| `--project`      | Yes      | —                    | GitLab project path, e.g. `org/group/repo`       |
| `--token`        | Yes      | —                    | GitLab private token with `read_repository` scope |
| `--branch`       | No       | `main`               | Branch or ref to fetch from                      |
| `--base-url`     | No       | `https://gitlab.com` | GitLab instance base URL                         |
| `--target-dir`   | No       | `sample_api_go`      | Local folder to download files into              |

## Usage

```bash
python skills/gitlab_reader/scripts/main.py \
  --project indiamart/search/product-search-screen \
  --token glpat-XXXXXXXXXXXX \
  --branch main \
  --base-url https://gitlab.indiamart.com \
  --target-dir product_search_api
```

## Behaviour

1. Walks the repository tree recursively via `/api/v4/projects/{id}/repository/tree`.
2. Filters to only `.py`, `.go`, and `.md` files.
3. Downloads each file via `/api/v4/projects/{id}/repository/files/{path}/raw`.
4. Mirrors the repository directory structure under `<target-dir>/`.
5. Handles GitLab pagination (`X-Next-Page` header) for large repos.

## Output

Files are saved to `<project_root>/<target-dir>/` preserving their original paths.
Downstream skills (`doc_ingestor`) can point at this directory for parsing.

## Notes

- The project path must be URL-encoded when passed to the API — the script handles this automatically.
- Files that fail to download are skipped with a warning; the run continues.
