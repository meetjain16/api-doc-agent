"""Entrypoint for the API DocAgent doc_ingestor skill."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parser import parse_project, scan_source_files


import argparse
import os

PROJECT_NAME = "API DocAgent"
SOURCE_REPO = os.getenv("SOURCE_REPO", "sample_api_go")
OUTPUT_FILE = "ingest.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API DocAgent ingestor")
    parser.add_argument("--source-repo", dest="source_repo", help="Local source folder containing Go service (overrides SOURCE_REPO env)")
    return parser.parse_args()


def endpoint_confidence(endpoint: dict[str, Any]) -> float:
    """Score endpoint metadata completeness for hackathon triage."""
    has_route = bool(endpoint.get("path") and endpoint.get("method") and endpoint.get("controller"))
    has_comments = bool(str(endpoint.get("comments", "")).strip())
    has_query_params = bool(endpoint.get("query_params"))

    if has_comments and has_query_params:
        return 1.0
    if has_route:
        return 0.7
    return 0.5


def build_ingestion_payload(project_root: Path) -> tuple[dict[str, Any], int]:
    """Parse the Go sample app and wrap the result in standardized metadata."""
    parsed = parse_project(project_root)
    scanned_files = len(scan_source_files(project_root))

    endpoints = []
    for endpoint in parsed.get("endpoints", []):
        enriched = dict(endpoint)
        enriched["confidence"] = endpoint_confidence(enriched)
        endpoints.append(enriched)

    structs = parsed.get("structs", [])
    payload = {
        "metadata": {
            "project": PROJECT_NAME,
            "source_repo": SOURCE_REPO,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_endpoints": len(endpoints),
            "total_structs": len(structs),
        },
        "endpoints": endpoints,
        "structs": structs,
    }
    return payload, scanned_files


def write_ingestion_json(payload: dict[str, Any], output_path: Path) -> None:
    """Write pretty-printed ingestion JSON, creating the output directory."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def repo_root() -> Path:
    """Resolve the API DocAgent repository root from this skill file."""
    return Path(__file__).resolve().parents[2]


def main() -> None:
    """Run ingestion for sample_api_go and save output/ingest.json."""
    args = _parse_args()
    root = repo_root()
    source_repo = args.source_repo or os.getenv("SOURCE_REPO") or SOURCE_REPO
    project_root = root / source_repo
    output_path = root / "output" / OUTPUT_FILE

    payload, scanned_files = build_ingestion_payload(project_root)
    write_ingestion_json(payload, output_path)

    print("API DocAgent ingestion complete")
    print(f"scanned files: {scanned_files}")
    print(f"endpoints found: {payload['metadata']['total_endpoints']}")
    print(f"structs found: {payload['metadata']['total_structs']}")
    print(f"output path: {output_path}")


if __name__ == "__main__":
    main()
