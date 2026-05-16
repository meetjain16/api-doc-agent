"""Lightweight schema drift comparator for API DocAgent.

Compares intentionally stale Markdown documentation against generated API
documentation JSON. This is intentionally regex/string based for hackathon
speed and easy explainability.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

COMMON_RESPONSE_FIELDS = {"status", "message", "data"}
RENAME_THRESHOLD = 0.72


def _repo_root() -> Path:
    """Return the API DocAgent repository root."""
    return Path(__file__).resolve().parents[2]


def _default_stale_docs_path() -> Path:
    return _repo_root() / "sample_api_go" / "docs" / "stale_docs.md"


def _default_generated_docs_path() -> Path:
    return _repo_root() / "output" / "generated_docs.json"


def load_stale_docs(path: Path | None = None) -> str:
    """Load stale Markdown documentation."""
    docs_path = path or _default_stale_docs_path()
    logger.info("Loading stale docs from %s", docs_path)
    return docs_path.read_text(encoding="utf-8")


def load_generated_docs(path: Path | None = None) -> dict[str, Any]:
    """Load generated documentation JSON."""
    docs_path = path or _default_generated_docs_path()
    logger.info("Loading generated docs from %s", docs_path)
    return json.loads(docs_path.read_text(encoding="utf-8"))


def _endpoint_key(method: str, path: str) -> tuple[str, str]:
    """Normalize an endpoint lookup key."""
    return method.upper().strip(), path.strip()


def split_endpoint_sections(markdown: str) -> dict[tuple[str, str], str]:
    """Split stale Markdown into endpoint sections keyed by method/path."""
    heading_pattern = re.compile(r"^##\s+([A-Z]+)\s+(\S+)\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(markdown))
    sections: dict[tuple[str, str], str] = {}

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        method, path = match.group(1), match.group(2)
        sections[_endpoint_key(method, path)] = markdown[start:end].strip()

    return sections


def _find_section(endpoint: dict[str, Any], sections: dict[tuple[str, str], str]) -> str:
    """Find exact method/path docs, then fall back to path-only docs."""
    method = str(endpoint.get("method", "")).upper()
    path = str(endpoint.get("path", ""))
    exact = sections.get(_endpoint_key(method, path))
    if exact:
        return exact

    for (_, section_path), section in sections.items():
        if section_path == path:
            return section

    return ""


def _terminal_field(token: str) -> str:
    """Return the final field name from paths like data.company.city."""
    cleaned = token.strip().strip("`").strip('"').strip("'").strip()
    cleaned = cleaned.rstrip(".,;:")
    if "." in cleaned:
        cleaned = cleaned.split(".")[-1]
    return cleaned


def _normalize_field_name(name: str) -> str:
    """Normalize snake/camel/dotted field names for comparison."""
    terminal = _terminal_field(name)
    return re.sub(r"[^a-z0-9]", "", terminal.lower())


def _split_words(name: str) -> set[str]:
    """Split camelCase, snake_case, and kebab-case names into comparable words."""
    terminal = _terminal_field(name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", terminal)
    spaced = re.sub(r"[^A-Za-z0-9]+", " ", spaced)
    return {part.lower() for part in spaced.split() if part}


def _similarity(left: str, right: str) -> float:
    """Compute a small renamed-field similarity score."""
    left_norm = _normalize_field_name(left)
    right_norm = _normalize_field_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    sequence_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_words = _split_words(left)
    right_words = _split_words(right)
    word_score = 0.0
    if left_words and right_words:
        word_score = len(left_words & right_words) / len(left_words | right_words)

    return max(sequence_score, word_score)


def _extract_code_fields(line: str) -> set[str]:
    """Extract backticked fields and dotted paths from one line."""
    fields: set[str] = set()
    for token in re.findall(r"`([^`]+)`", line):
        field = _terminal_field(token)
        if field:
            fields.add(field)
    return fields


def _extract_json_keys(markdown: str) -> set[str]:
    """Extract JSON object keys from fenced examples."""
    fields: set[str] = set()
    for block in re.findall(r"```json\s*(.*?)```", markdown, flags=re.DOTALL | re.IGNORECASE):
        for key in re.findall(r'"([A-Za-z_][A-Za-z0-9_\-]*)"\s*:', block):
            fields.add(_terminal_field(key))
    return fields


def _extract_request_table_fields(markdown: str) -> set[str]:
    """Extract first-column fields from simple Markdown request tables."""
    fields: set[str] = set()
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() in {"field", ""}:
            continue

        # Only the stale docs' simple tables use Field as the first column.
        if len(cells) >= 2:
            fields.add(_terminal_field(cells[0]))

    return fields


def extract_documented_request_fields(section: str) -> set[str]:
    """Extract fields that old docs actively document as request inputs."""
    return _extract_request_table_fields(section)


def extract_documented_response_fields(section: str) -> set[str]:
    """Extract fields that old docs actively document as response outputs."""
    fields = _extract_json_keys(section)

    for line in section.splitlines():
        lower = line.lower()
        if "actual response" in lower or "real api" in lower or "deprecated" in lower:
            continue
        if "old docs" in lower and ("response" in lower or "records contain" in lower or "top-level" in lower):
            fields.update(_extract_code_fields(line))

    return fields


def extract_deprecated_mentions(section: str) -> set[str]:
    """Extract deprecated fields explicitly called out in stale docs."""
    deprecated: set[str] = set()
    for line in section.splitlines():
        lower = line.lower()
        if "deprecated" not in lower:
            continue

        # Prefer the phrase nearest to "deprecated" so adjacent current fields
        # on the same sentence are not incorrectly marked as deprecated.
        focused_line = line
        if "called" in lower:
            focused_line = line[lower.index("called") :]
        if " and uses " in focused_line.lower():
            focused_line = focused_line[: focused_line.lower().index(" and uses ")]

        fields = list(_extract_code_fields(focused_line))
        if fields:
            deprecated.add(fields[0])
    return deprecated


def _field_name(field: dict[str, Any]) -> str:
    """Prefer JSON names, then form tags, then Go names."""
    return str(field.get("json") or field.get("form") or field.get("name") or "").strip()


def _actual_response_fields(endpoint: dict[str, Any]) -> list[str]:
    """Return unique generated response field names."""
    fields: list[str] = []
    seen: set[str] = set()
    for field in endpoint.get("response_fields", []):
        name = _field_name(field)
        if name and name not in seen:
            seen.add(name)
            fields.append(name)
    return fields


def _actual_request_fields(endpoint: dict[str, Any]) -> list[str]:
    """Return unique generated request/query field names."""
    fields: list[str] = []
    seen: set[str] = set()

    for name in endpoint.get("query_params", []):
        text = str(name).strip()
        if text and text not in seen:
            seen.add(text)
            fields.append(text)

    for field in endpoint.get("request_fields", []):
        name = _field_name(field)
        if name and name not in seen:
            seen.add(name)
            fields.append(name)

    return fields


def _best_replacement(field: str, actual_fields: list[str]) -> tuple[str, float] | None:
    """Find a likely renamed replacement in current generated fields."""
    if not field:
        return None

    normalized = _normalize_field_name(field)
    for actual in actual_fields:
        if actual != field and _normalize_field_name(actual) == normalized:
            return actual, 1.0

    scored = [(actual, _similarity(field, actual)) for actual in actual_fields]
    scored.sort(key=lambda item: item[1], reverse=True)
    if scored and scored[0][1] >= RENAME_THRESHOLD:
        return scored[0]

    return None


def _issue(
    issue_type: str,
    field: str,
    *,
    severity: str,
    suggested_replacement: str = "",
    detail: str = "",
) -> dict[str, Any]:
    """Create one structured drift issue."""
    payload: dict[str, Any] = {
        "type": issue_type,
        "field": field,
        "severity": severity,
    }
    if suggested_replacement:
        payload["suggested_replacement"] = suggested_replacement
    if detail:
        payload["detail"] = detail
    return payload


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove repeated issues caused by duplicate GET/POST or nested fields."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (
            str(issue.get("type", "")),
            str(issue.get("field", "")),
            str(issue.get("suggested_replacement", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _score_endpoint_severity(issues: list[dict[str, Any]]) -> str:
    """Score endpoint severity from issue severities."""
    if any(issue.get("severity") == "HIGH" for issue in issues):
        return "HIGH"
    if any(issue.get("severity") == "MEDIUM" for issue in issues):
        return "MEDIUM"
    if issues:
        return "LOW"
    return "NONE"


def compare_endpoint(endpoint: dict[str, Any], stale_section: str) -> dict[str, Any]:
    """Compare one generated endpoint against one stale Markdown section."""
    issues: list[dict[str, Any]] = []
    documented_request = extract_documented_request_fields(stale_section)
    documented_response = extract_documented_response_fields(stale_section)
    deprecated_mentions = extract_deprecated_mentions(stale_section)
    actual_request = _actual_request_fields(endpoint)
    actual_response = _actual_response_fields(endpoint)

    documented_response_norm = {_normalize_field_name(field) for field in documented_response}
    documented_request_norm = {_normalize_field_name(field) for field in documented_request}

    for field in sorted(documented_response):
        if field in actual_response:
            continue

        replacement = _best_replacement(field, actual_response)
        if replacement:
            replacement_name, score = replacement
            issues.append(
                _issue(
                    "POSSIBLE_RENAMED_FIELD",
                    field,
                    severity="HIGH",
                    suggested_replacement=replacement_name,
                    detail=f"Similarity score {score:.2f}; stale response field is not present exactly.",
                )
            )
            issues.append(
                _issue(
                    "RESPONSE_MISMATCH",
                    field,
                    severity="HIGH",
                    suggested_replacement=replacement_name,
                    detail="Documented response field differs from generated response schema.",
                )
            )
        else:
            issues.append(
                _issue(
                    "REMOVED_FIELD",
                    field,
                    severity="HIGH",
                    detail="Field appears in stale response docs but not in generated response fields.",
                )
            )

    for field in actual_response:
        normalized = _normalize_field_name(field)
        if normalized in documented_response_norm or field in COMMON_RESPONSE_FIELDS:
            continue
        issues.append(
            _issue(
                "UNDOCUMENTED_RESPONSE_FIELD",
                field,
                severity="MEDIUM",
                detail="Generated response field is not documented in stale Markdown.",
            )
        )

    for field in actual_request:
        normalized = _normalize_field_name(field)
        if normalized in documented_request_norm:
            continue
        issues.append(
            _issue(
                "UNDOCUMENTED_QUERY_OR_REQUEST_FIELD",
                field,
                severity="MEDIUM",
                detail="Generated request/query field is not documented in stale Markdown.",
            )
        )

    for field in actual_response:
        normalized = _normalize_field_name(field)
        mentioned = normalized in {_normalize_field_name(name) for name in deprecated_mentions}
        looks_legacy = "legacy" in normalized or "deprecated" in normalized
        if mentioned or looks_legacy:
            issues.append(
                _issue(
                    "DEPRECATED_FIELD",
                    field,
                    severity="MEDIUM",
                    detail="Field is explicitly deprecated in stale docs or appears to be a legacy compatibility field.",
                )
            )

    issues = _dedupe_issues(issues)

    return {
        "endpoint": endpoint.get("path", ""),
        "method": endpoint.get("method", ""),
        "severity": _score_endpoint_severity(issues),
        "documented_request_fields": sorted(documented_request),
        "documented_response_fields": sorted(documented_response),
        "generated_request_fields": actual_request,
        "generated_response_fields": actual_response,
        "issues": issues,
    }


def compare_drift(
    generated_docs_path: Path | None = None,
    stale_docs_path: Path | None = None,
) -> dict[str, Any]:
    """Compare stale Markdown docs with generated docs and return structured drift."""
    stale_markdown = load_stale_docs(stale_docs_path)
    generated_docs = load_generated_docs(generated_docs_path)
    sections = split_endpoint_sections(stale_markdown)
    results: list[dict[str, Any]] = []

    for endpoint in generated_docs.get("endpoints", []):
        path = str(endpoint.get("path", "")).strip()
        if not path:
            logger.warning("Skipping generated endpoint with missing path: %s", endpoint)
            continue

        section = _find_section(endpoint, sections)
        if not section:
            results.append(
                {
                    "endpoint": path,
                    "method": endpoint.get("method", ""),
                    "severity": "HIGH",
                    "documented_request_fields": [],
                    "documented_response_fields": [],
                    "generated_request_fields": _actual_request_fields(endpoint),
                    "generated_response_fields": _actual_response_fields(endpoint),
                    "issues": [
                        _issue(
                            "MISSING_ENDPOINT_DOCS",
                            path,
                            severity="HIGH",
                            detail="No matching endpoint section found in stale Markdown docs.",
                        )
                    ],
                }
            )
            continue

        results.append(compare_endpoint(endpoint, section))

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_generated_docs": str(generated_docs_path or _default_generated_docs_path()),
            "source_stale_docs": str(stale_docs_path or _default_stale_docs_path()),
            "endpoints_compared": len(results),
            "high_severity_endpoints": sum(1 for result in results if result["severity"] == "HIGH"),
        },
        "results": results,
    }


def main() -> None:
    """Run comparator directly and print JSON for quick demos."""
    print(json.dumps(compare_drift(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
