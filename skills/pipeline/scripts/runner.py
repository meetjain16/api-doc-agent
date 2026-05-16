"""End-to-end pipeline runner for API DocAgent.

Reads repos.yaml, fetches source files from GitLab, runs the appropriate
parser, generates AI documentation, and runs drift detection.
Output is written to output/repos/{slug}/.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

_ROOT = Path(__file__).resolve().parents[3]
_SKILLS = _ROOT / "skills"

# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------

def _ensure_path(dir_str: str) -> None:
    if dir_str not in sys.path:
        sys.path.insert(0, dir_str)


def _load_mod(file_path: Path, unique_name: str, force_reload: bool = False) -> Any:
    if not force_reload and unique_name in sys.modules:
        return sys.modules[unique_name]
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    if spec is None:
        raise ImportError(f"Cannot load {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Add skill scripts/ dirs to sys.path so relative-import fallbacks work inside each module
_ensure_path(str(_SKILLS / "doc_ingestor" / "scripts"))
_ensure_path(str(_SKILLS / "doc_generator" / "scripts"))
_ensure_path(str(_SKILLS / "drift_detector" / "scripts"))

# Load skill modules with unique names to avoid conflicts
_go_parser = _load_mod(_SKILLS / "doc_ingestor" / "scripts" / "parser.py", "_docagent_go_parser")
# Always reload the FastAPI parser so code changes take effect without server restart
_fp_parser = _load_mod(_SKILLS / "doc_ingestor" / "scripts" / "fastapi_parser.py", "_docagent_fp_parser", force_reload=True)
_doc_gen = _load_mod(_SKILLS / "doc_generator" / "scripts" / "main.py", "_docagent_doc_gen")
_drift = _load_mod(_SKILLS / "drift_detector" / "scripts" / "main.py", "_docagent_drift")

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def repo_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_repos_config(config_path: Path | None = None) -> list[dict[str, Any]]:
    path = config_path or _ROOT / "repos.yaml"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        return config.get("repos", []) if isinstance(config, dict) else []
    except Exception as exc:
        logger.error("Failed to load repos.yaml: %s", exc)
        return []


def get_repo_by_name(name: str, repos: list[dict] | None = None) -> dict[str, Any] | None:
    for repo in repos or load_repos_config():
        if repo.get("name") == name:
            return repo
    return None

# ---------------------------------------------------------------------------
# GitLab fetcher
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS = {".py", ".go", ".md"}


def _fetch_tree(session: requests.Session, base_url: str, project: str, branch: str) -> list[dict]:
    entries: list[dict] = []
    page = 1
    while True:
        url = (
            f"{base_url.rstrip('/')}/api/v4/projects"
            f"/{quote_plus(project, safe='')}/repository/tree"
            f"?recursive=true&per_page=100&ref={quote_plus(branch)}&page={page}"
        )
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list):
            break
        entries.extend(batch)
        if not resp.headers.get("X-Next-Page"):
            break
        page = int(resp.headers["X-Next-Page"])
    return entries


def _fetch_file(session: requests.Session, base_url: str, project: str, file_path: str, branch: str) -> bytes:
    url = (
        f"{base_url.rstrip('/')}/api/v4/projects"
        f"/{quote_plus(project, safe='')}/repository/files"
        f"/{quote_plus(file_path, safe='')}/raw?ref={quote_plus(branch)}"
    )
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def fetch_repo(repo_config: dict[str, Any], target_dir: Path) -> int:
    """Download source files from GitLab into target_dir. Returns file count."""
    import shutil
    if target_dir.exists():
        shutil.rmtree(target_dir)

    session = requests.Session()
    session.headers["PRIVATE-TOKEN"] = repo_config["token"]

    base_url = repo_config.get("base_url", "https://gitlab.com")
    project = repo_config["project"]
    branch = repo_config.get("branch", "main")

    logger.info("Fetching %s (%s) from %s", project, branch, base_url)
    tree = _fetch_tree(session, base_url, project, branch)
    blobs = [e for e in tree if e.get("type") == "blob"]

    downloaded = 0
    for entry in blobs:
        file_path = str(entry.get("path", ""))
        if not file_path:
            continue
        if Path(file_path).suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        try:
            content = _fetch_file(session, base_url, project, file_path, branch)
        except Exception as exc:
            logger.warning("Skipping %s: %s", file_path, exc)
            continue
        out = target_dir / file_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
        downloaded += 1

    logger.info("Fetched %d files into %s", downloaded, target_dir)
    return downloaded

# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _endpoint_confidence(endpoint: dict[str, Any]) -> float:
    has_route = bool(endpoint.get("path") and endpoint.get("method") and endpoint.get("controller"))
    has_comments = bool(str(endpoint.get("comments", "")).strip())
    has_query_params = bool(endpoint.get("query_params"))
    if has_comments and has_query_params:
        return 1.0
    if has_route:
        return 0.7
    return 0.5


def run_ingest(project_root: Path, source_type: str) -> dict[str, Any]:
    source_type = (source_type or "go").lower()
    if source_type == "fastapi":
        # Reload on every call so file edits take effect without server restart
        fp = _load_mod(_SKILLS / "doc_ingestor" / "scripts" / "fastapi_parser.py", "_docagent_fp_parser", force_reload=True)
        parsed = fp.parse_fastapi_project(project_root)
    else:
        parsed = _go_parser.parse_project(project_root)

    endpoints = [
        {**ep, "confidence": _endpoint_confidence(ep)}
        for ep in parsed.get("endpoints", [])
    ]
    structs = parsed.get("structs", [])

    return {
        "metadata": {
            "project": "API DocAgent",
            "source_repo": project_root.name,
            "source_type": source_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_endpoints": len(endpoints),
            "total_structs": len(structs),
        },
        "endpoints": endpoints,
        "structs": structs,
    }

# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(repo_config: dict[str, Any]) -> dict[str, Any]:
    """Run the full pipeline for one repo config entry and return a status dict."""
    slug = repo_slug(repo_config["name"])
    repo_output = _ROOT / "output" / "repos" / slug
    src_dir = repo_output / "src"

    logger.info("=== Pipeline: %s ===", repo_config["name"])

    # 1. Fetch
    try:
        file_count = fetch_repo(repo_config, src_dir)
    except Exception as exc:
        logger.error("Fetch failed: %s", exc)
        return {"status": "FAILED", "stage": "fetch", "error": str(exc), "slug": slug}

    # 2. Ingest
    source_type = repo_config.get("source_type", "go")
    try:
        ingest_payload = run_ingest(src_dir, source_type)
        _write_json(repo_output / "ingest.json", ingest_payload)
        ep_count = ingest_payload["metadata"]["total_endpoints"]
        st_count = ingest_payload["metadata"]["total_structs"]
        logger.info("Ingest: %d endpoints, %d structs", ep_count, st_count)
    except Exception as exc:
        logger.error("Ingest failed: %s", exc)
        return {"status": "FAILED", "stage": "ingest", "error": str(exc), "slug": slug}

    # 3. Generate docs
    try:
        docs_payload = _doc_gen.generate_docs(ingest_payload)
        _write_json(repo_output / "generated_docs.json", docs_payload)
        _write_text(repo_output / "generated_docs.md", _doc_gen._render_full_markdown(docs_payload))
        docs_count = docs_payload["metadata"]["generated_endpoints"]
        logger.info("Docs generated: %d", docs_count)
    except Exception as exc:
        logger.error("Doc generation failed: %s", exc)
        return {"status": "FAILED", "stage": "doc_generation", "error": str(exc), "slug": slug}

    # 4. Drift detection (best-effort — no stale docs is handled gracefully)
    stale_path: Path | None = src_dir / "docs" / "stale_docs.md"
    if not stale_path.exists():
        stale_path = None
    try:
        _drift.run_drift_detection(
            generated_docs_path=repo_output / "generated_docs.json",
            stale_docs_path=stale_path,
            output_dir=repo_output,
        )
        logger.info("Drift detection complete")
    except Exception as exc:
        logger.warning("Drift detection failed (non-fatal): %s", exc)

    return {
        "status": "OK",
        "slug": slug,
        "output_dir": str(repo_output),
        "files_fetched": file_count,
        "endpoints": ep_count,
        "structs": st_count,
        "docs_generated": docs_count,
    }


def run_by_name(repo_name: str) -> dict[str, Any]:
    """Load repos.yaml, find the named repo, and run its pipeline."""
    repos = load_repos_config()
    repo_config = get_repo_by_name(repo_name, repos)
    if not repo_config:
        return {"status": "FAILED", "stage": "config", "error": f"Repo '{repo_name}' not found in repos.yaml"}
    return run_pipeline(repo_config)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run API DocAgent pipeline for a repo from repos.yaml")
    parser.add_argument("--repo", required=True, help="Repo name as it appears in repos.yaml")
    args = parser.parse_args()

    result = run_by_name(args.repo)
    print(json.dumps(result, indent=2))
