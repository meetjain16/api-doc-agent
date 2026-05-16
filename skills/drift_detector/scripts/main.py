"""Entrypoint for API DocAgent drift detection.

Runs schema comparison, generates engineering-friendly reports, and writes
breaking change artifacts under output/.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .comparator import compare_drift
    from .report_generator import generate_report
except ImportError:  # Allow running this file directly.
    from comparator import compare_drift
    from report_generator import generate_report


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def _repo_root() -> Path:
    """Return the API DocAgent repository root."""
    return Path(__file__).resolve().parents[2]


def _default_generated_docs_path() -> Path:
    return _repo_root() / "output" / "generated_docs.json"


def _default_stale_docs_path() -> Path:
    return _repo_root() / "sample_api_go" / "docs" / "stale_docs.md"


def _default_output_dir() -> Path:
    return _repo_root() / "output"


def _count_issues(results: list[dict[str, Any]]) -> int:
    """Count all drift issues."""
    return sum(len(result.get("issues", [])) for result in results)


def _count_high_issues(results: list[dict[str, Any]]) -> int:
    """Count high-severity drift issues."""
    return sum(
        1
        for result in results
        for issue in result.get("issues", [])
        if str(issue.get("severity", "")).upper() == "HIGH"
    )


def _collect_breaking_changes(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten high-severity issues into PR/CI-friendly breaking change rows."""
    breaking_changes: list[dict[str, Any]] = []

    for result in results:
        for issue in result.get("issues", []):
            if str(issue.get("severity", "")).upper() != "HIGH":
                continue

            breaking_changes.append(
                {
                    "endpoint": result.get("endpoint", ""),
                    "method": result.get("method", ""),
                    "type": issue.get("type", ""),
                    "field": issue.get("field", ""),
                    "suggested_replacement": issue.get("suggested_replacement", ""),
                    "detail": issue.get("detail", ""),
                }
            )

    return breaking_changes


def _missing_files(paths: list[Path]) -> list[str]:
    """Return missing file paths without raising."""
    return [str(path) for path in paths if not path.exists()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_markdown(path: Path, markdown: str) -> None:
    """Write Markdown output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def _build_failure_payload(missing: list[str]) -> dict[str, Any]:
    """Build a safe failure payload when inputs are unavailable."""
    return {
        "metadata": {
            "project": "API DocAgent",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAILED",
            "reason": "Missing required input files",
            "missing_files": missing,
            "endpoints_analyzed": 0,
            "drift_issues_found": 0,
            "high_severity_issues": 0,
        },
        "breaking_changes": [],
        "drift_results": [],
        "alerts": [],
        "pr_breaking_change_report": "",
    }


def _failure_markdown(payload: dict[str, Any]) -> str:
    """Render missing-file failures as Markdown for demos and CI logs."""
    missing = payload["metadata"].get("missing_files", [])
    missing_lines = "\n".join(f"- `{path}`" for path in missing) or "- None"

    return f"""# API DocAgent Breaking Change Report

Status: `FAILED`

The drift detector could not run because required input files are missing.

## Missing Files
{missing_lines}
"""


def _build_success_payload(
    drift_results: dict[str, Any],
    report: dict[str, Any],
    generated_docs_path: Path,
    stale_docs_path: Path,
) -> dict[str, Any]:
    """Combine comparator and report output into one structured artifact."""
    results = drift_results.get("results", [])
    issue_count = _count_issues(results)
    high_issue_count = _count_high_issues(results)

    return {
        "metadata": {
            "project": "API DocAgent",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "OK",
            "source_generated_docs": str(generated_docs_path),
            "source_stale_docs": str(stale_docs_path),
            "endpoints_analyzed": len(results),
            "drift_issues_found": issue_count,
            "high_severity_issues": high_issue_count,
            "high_severity_endpoints": drift_results.get("metadata", {}).get("high_severity_endpoints", 0),
        },
        "breaking_changes": _collect_breaking_changes(results),
        "drift_results": results,
        "alerts": report.get("alerts", []),
        "pr_breaking_change_report": report.get("pr_breaking_change_report", ""),
    }


def _build_markdown(report: dict[str, Any]) -> str:
    """Combine PR-style and summary Markdown into one report file."""
    pr_report = report.get("pr_breaking_change_report", "").strip()
    summary = report.get("markdown_summary", "").strip()

    if not pr_report and not summary:
        return "# API DocAgent Breaking Change Report\n\nNo drift report content generated.\n"

    if not pr_report:
        return summary + "\n"
    if not summary:
        return pr_report + "\n"

    return f"{pr_report}\n\n---\n\n{summary}\n"


def _self_analysis(generated_docs: dict[str, Any]) -> dict[str, Any]:
    """Analyse generated_docs.json without stale docs.

    Flags: AI fallback endpoints, undocumented query params, missing request/response fields.
    """
    from comparator import (
        _actual_request_fields, _actual_response_fields,
        _score_endpoint_severity, _issue, _dedupe_issues,
    )

    results: list[dict[str, Any]] = []
    for endpoint in generated_docs.get("endpoints", []):
        path = str(endpoint.get("path", "")).strip()
        if not path:
            continue
        issues: list[dict[str, Any]] = []
        ai_sections = endpoint.get("ai_sections", {})
        status = ai_sections.get("generation_status", "fallback")

        if status == "fallback":
            issues.append(_issue(
                "NO_AI_DOCUMENTATION", path,
                severity="HIGH",
                detail="AI documentation was not generated. Add a valid LLM key and re-run the pipeline.",
            ))

        for param in endpoint.get("query_params", []):
            issues.append(_issue(
                "UNDOCUMENTED_QUERY_OR_REQUEST_FIELD", str(param),
                severity="LOW",
                detail="Query parameter found in source code with no documentation.",
            ))

        req_fields = _actual_request_fields(endpoint)
        resp_fields = _actual_response_fields(endpoint)

        if not req_fields and not resp_fields and endpoint.get("confidence", 0) >= 0.7:
            issues.append(_issue(
                "MISSING_SCHEMA", path,
                severity="MEDIUM",
                detail="No request or response fields resolved — structs may be in external packages.",
            ))

        issues = _dedupe_issues(issues)
        results.append({
            "endpoint": path,
            "method": endpoint.get("method", ""),
            "severity": _score_endpoint_severity(issues),
            "documented_request_fields": [],
            "documented_response_fields": [],
            "generated_request_fields": req_fields,
            "generated_response_fields": resp_fields,
            "issues": issues,
        })

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "self-analysis (no stale docs)",
            "endpoints_compared": len(results),
            "high_severity_endpoints": sum(1 for r in results if r["severity"] == "HIGH"),
        },
        "results": results,
    }


def run_drift_detection(
    generated_docs_path: Path | None = None,
    stale_docs_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run drift detection and save JSON/Markdown artifacts.

    When no stale_docs_path is provided (or the file doesn't exist), runs
    self-analysis mode: flags AI failures, undocumented params, and missing schemas.
    """
    generated_path = generated_docs_path or _default_generated_docs_path()
    target_dir = output_dir or _default_output_dir()
    json_output_path = target_dir / "breaking_changes.json"
    markdown_output_path = target_dir / "breaking_changes.md"

    missing_generated = _missing_files([generated_path])
    if missing_generated:
        logger.error("Drift detection skipped; missing: %s", missing_generated)
        payload = _build_failure_payload(missing_generated)
        _write_json(json_output_path, payload)
        _write_markdown(markdown_output_path, _failure_markdown(payload))
        return payload

    # ── Stale-docs mode vs self-analysis mode ────────────────────
    stale_path = stale_docs_path if stale_docs_path and stale_docs_path.exists() else None

    if stale_path:
        logger.info("Running drift comparison against stale docs: %s", stale_path)
        drift_results = compare_drift(generated_docs_path=generated_path, stale_docs_path=stale_path)
    else:
        logger.info("No stale docs found — running self-analysis mode")
        import json as _json
        generated_docs = _json.loads(generated_path.read_text(encoding="utf-8"))
        drift_results = _self_analysis(generated_docs)

    logger.info("Generating human-readable drift report")
    report = generate_report(drift_results)
    payload = _build_success_payload(drift_results, report, generated_path, stale_path or Path("(self-analysis)"))

    _write_json(json_output_path, payload)
    _write_markdown(markdown_output_path, _build_markdown(report))

    payload["metadata"]["json_output"] = str(json_output_path)
    payload["metadata"]["markdown_output"] = str(markdown_output_path)
    return payload


def _print_summary(payload: dict[str, Any]) -> None:
    """Print concise console output for hackathon demos."""
    metadata = payload.get("metadata", {})
    print("API DocAgent drift detection complete")
    print(f"Status: {metadata.get('status', 'UNKNOWN')}")
    print(f"Endpoints analyzed: {metadata.get('endpoints_analyzed', 0)}")
    print(f"Drift issues found: {metadata.get('drift_issues_found', 0)}")
    print(f"High severity issues: {metadata.get('high_severity_issues', 0)}")

    if metadata.get("json_output"):
        print(f"JSON output: {metadata['json_output']}")
    if metadata.get("markdown_output"):
        print(f"Markdown output: {metadata['markdown_output']}")
    if metadata.get("missing_files"):
        print("Missing files:")
        for path in metadata["missing_files"]:
            print(f"- {path}")


def main() -> None:
    """Run the drift detector entrypoint."""
    payload = run_drift_detection()
    _print_summary(payload)


if __name__ == "__main__":
    main()
