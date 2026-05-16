"""Human-readable drift reports for API DocAgent.

This module turns structured comparator output into engineering-style alerts,
Markdown summaries, and PR review comments. It intentionally stays small and
framework-free so hackathon demos can reuse it from a CLI, notebook, or UI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from .comparator import compare_drift
except ImportError:  # Allow running this file directly.
    from comparator import compare_drift


SEVERITY_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}

ISSUE_TITLES = {
    "REMOVED_FIELD": "Field removed",
    "POSSIBLE_RENAMED_FIELD": "Possible field rename",
    "RESPONSE_MISMATCH": "Response schema mismatch",
    "UNDOCUMENTED_RESPONSE_FIELD": "Undocumented response field",
    "UNDOCUMENTED_QUERY_OR_REQUEST_FIELD": "Undocumented request/query field",
    "DEPRECATED_FIELD": "Deprecated field still present",
    "MISSING_ENDPOINT_DOCS": "Endpoint documentation missing",
}

ISSUE_IMPACTS = {
    "REMOVED_FIELD": "Potential frontend/schema incompatibility.",
    "POSSIBLE_RENAMED_FIELD": "Consumers may read the old field and miss the new response value.",
    "RESPONSE_MISMATCH": "Generated schema and stale docs disagree; client contracts may drift.",
    "UNDOCUMENTED_RESPONSE_FIELD": "Consumers may not know this response field exists.",
    "UNDOCUMENTED_QUERY_OR_REQUEST_FIELD": "Clients may miss supported filters or required inputs.",
    "DEPRECATED_FIELD": "Compatibility field should be documented as deprecated or removed intentionally.",
    "MISSING_ENDPOINT_DOCS": "Endpoint may be absent from the internal API catalog.",
}


def _clean(value: Any, default: str = "Not available") -> str:
    """Convert optional values into display-safe text."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value)


def _endpoint_label(result: dict[str, Any]) -> str:
    """Render METHOD path."""
    method = _clean(result.get("method"), "")
    endpoint = _clean(result.get("endpoint"), "")
    return f"{method} {endpoint}".strip()


def _severity_rank(value: str) -> int:
    """Return numeric severity for sorting."""
    return SEVERITY_ORDER.get(value.upper(), 0)


def _sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort endpoints by severity and number of issues."""
    return sorted(
        results,
        key=lambda item: (_severity_rank(_clean(item.get("severity"), "NONE")), len(item.get("issues", []))),
        reverse=True,
    )


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort issues by severity, then type."""
    return sorted(
        issues,
        key=lambda item: (_severity_rank(_clean(item.get("severity"), "NONE")), _clean(item.get("type"))),
        reverse=True,
    )


def _issue_title(issue: dict[str, Any]) -> str:
    """Map issue type to a review-friendly title."""
    issue_type = _clean(issue.get("type"), "UNKNOWN")
    return ISSUE_TITLES.get(issue_type, issue_type.replace("_", " ").title())


def _issue_impact(issue: dict[str, Any]) -> str:
    """Map issue type to a useful engineering impact statement."""
    issue_type = _clean(issue.get("type"), "UNKNOWN")
    return ISSUE_IMPACTS.get(issue_type, "API documentation and implementation should be reviewed.")


def _breaking_change_heading(issue: dict[str, Any]) -> str:
    """Use a stronger heading for high-severity API contract drift."""
    severity = _clean(issue.get("severity"), "LOW").upper()
    if severity == "HIGH":
        return "BREAKING CHANGE DETECTED"
    if severity == "MEDIUM":
        return "API DRIFT WARNING"
    return "API DRIFT NOTICE"


def _format_suggested_replacement(issue: dict[str, Any]) -> str:
    """Render replacement guidance when comparator detected a likely rename."""
    replacement = _clean(issue.get("suggested_replacement"), "")
    if not replacement:
        return "Not available"
    return replacement


def format_engineering_alert(result: dict[str, Any], issue: dict[str, Any]) -> str:
    """Format one issue like an internal engineering review comment."""
    detail = _clean(issue.get("detail"), "")
    detail_block = f"\nDetail:\n{detail}\n" if detail and detail != "Not available" else ""

    return f"""{_breaking_change_heading(issue)}
Endpoint:
{_endpoint_label(result)}

Severity:
{_clean(issue.get("severity"), "LOW").upper()}

Issue:
{_issue_title(issue)}: {_clean(issue.get("field"))}

Suggested replacement:
{_format_suggested_replacement(issue)}

Impact:
{_issue_impact(issue)}
{detail_block}"""


def build_engineering_alerts(drift_results: dict[str, Any]) -> list[str]:
    """Generate one alert per drift issue."""
    alerts: list[str] = []
    for result in _sort_results(drift_results.get("results", [])):
        for issue in _sort_issues(result.get("issues", [])):
            alerts.append(format_engineering_alert(result, issue))
    return alerts


def _count_by_severity(results: list[dict[str, Any]]) -> dict[str, int]:
    """Count endpoints by endpoint-level severity."""
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    for result in results:
        severity = _clean(result.get("severity"), "NONE").upper()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _count_issues(results: list[dict[str, Any]]) -> int:
    """Count all drift issues."""
    return sum(len(result.get("issues", [])) for result in results)


def _markdown_issue_list(result: dict[str, Any], max_issues: int = 8) -> str:
    """Render top issues for one endpoint in Markdown."""
    issues = _sort_issues(result.get("issues", []))
    if not issues:
        return "- No drift detected."

    lines: list[str] = []
    for issue in issues[:max_issues]:
        replacement = _format_suggested_replacement(issue)
        replacement_text = f" Suggested replacement: `{replacement}`." if replacement != "Not available" else ""
        lines.append(
            "- **{severity}** `{type}` on `{field}`: {impact}{replacement}".format(
                severity=_clean(issue.get("severity"), "LOW").upper(),
                type=_clean(issue.get("type")),
                field=_clean(issue.get("field")),
                impact=_issue_impact(issue),
                replacement=replacement_text,
            )
        )

    hidden_count = len(issues) - max_issues
    if hidden_count > 0:
        lines.append(f"- Plus {hidden_count} additional issue(s).")

    return "\n".join(lines)


def build_markdown_summary(drift_results: dict[str, Any]) -> str:
    """Generate a concise Markdown drift summary."""
    metadata = drift_results.get("metadata", {})
    results = _sort_results(drift_results.get("results", []))
    counts = _count_by_severity(results)

    sections = [
        "# API DocAgent Drift Report",
        "",
        f"Generated at: `{_clean(metadata.get('generated_at'), datetime.now(timezone.utc).isoformat())}`",
        f"Endpoints compared: `{_clean(metadata.get('endpoints_compared'), str(len(results)))}`",
        f"Total issues: `{_count_issues(results)}`",
        "",
        "## Severity Summary",
        "",
        "| Severity | Endpoint Count |",
        "| --- | ---: |",
        f"| HIGH | {counts.get('HIGH', 0)} |",
        f"| MEDIUM | {counts.get('MEDIUM', 0)} |",
        f"| LOW | {counts.get('LOW', 0)} |",
        f"| NONE | {counts.get('NONE', 0)} |",
        "",
        "## Endpoint Findings",
    ]

    for result in results:
        sections.extend(
            [
                "",
                f"### {_endpoint_label(result)}",
                "",
                f"Severity: `{_clean(result.get('severity'), 'NONE').upper()}`",
                "",
                _markdown_issue_list(result),
            ]
        )

    return "\n".join(sections).rstrip() + "\n"


def _is_pr_relevant(issue: dict[str, Any]) -> bool:
    """Return whether this issue should appear in a PR-style breaking report."""
    return _clean(issue.get("severity"), "LOW").upper() in {"HIGH", "MEDIUM"}


def build_pr_breaking_change_report(drift_results: dict[str, Any]) -> str:
    """Generate a PR-review style report focused on actionable drift."""
    results = _sort_results(drift_results.get("results", []))
    lines = [
        "## API Contract Drift Review",
        "",
        "The generated API schema was compared against the existing Markdown documentation.",
        "Review the items below before merging API or documentation changes.",
    ]

    has_findings = False
    for result in results:
        relevant_issues = [issue for issue in _sort_issues(result.get("issues", [])) if _is_pr_relevant(issue)]
        if not relevant_issues:
            continue

        has_findings = True
        lines.extend(["", f"### {_endpoint_label(result)}", ""])
        for issue in relevant_issues:
            replacement = _format_suggested_replacement(issue)
            lines.extend(
                [
                    f"**{_breaking_change_heading(issue)}**",
                    "",
                    f"- Severity: `{_clean(issue.get('severity'), 'LOW').upper()}`",
                    f"- Issue: {_issue_title(issue)} on `{_clean(issue.get('field'))}`",
                    f"- Suggested replacement: `{replacement}`",
                    f"- Impact: {_issue_impact(issue)}",
                ]
            )
            detail = _clean(issue.get("detail"), "")
            if detail and detail != "Not available":
                lines.append(f"- Detail: {detail}")
            lines.append("")

    if not has_findings:
        lines.extend(["", "No HIGH or MEDIUM API drift findings detected."])

    return "\n".join(lines).rstrip() + "\n"


def generate_report(drift_results: dict[str, Any]) -> dict[str, Any]:
    """Return all report formats from structured drift results."""
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "API DocAgent drift_detector.report_generator",
            "endpoint_count": len(drift_results.get("results", [])),
            "issue_count": _count_issues(drift_results.get("results", [])),
        },
        "alerts": build_engineering_alerts(drift_results),
        "markdown_summary": build_markdown_summary(drift_results),
        "pr_breaking_change_report": build_pr_breaking_change_report(drift_results),
    }


def main() -> None:
    """Run comparator and print the Markdown summary for quick demos."""
    drift_results = compare_drift()
    report = generate_report(drift_results)
    print(report["markdown_summary"])


if __name__ == "__main__":
    main()
