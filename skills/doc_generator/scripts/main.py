"""Entrypoint for AI-powered API documentation generation.

Reads API ingestion metadata from output/ingest.json, asks the OpenAI-backed
doc generator for structured endpoint documentation, and writes JSON plus
Markdown artifacts for hackathon demos.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    from .openai_client import generate_json
    from .prompts import build_doc_prompt
except ImportError:  # Allow running this file directly.
    from openai_client import generate_json
    from prompts import build_doc_prompt


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


DOC_KEYS = (
    "endpoint_summary",
    "business_summary",
    "request_explanation",
    "response_explanation",
    "validation_notes",
    "sample_curl",
    "edge_cases",
    "openapi_schema_summary",
)


def _repo_root() -> Path:
    """Return the API DocAgent repository root."""
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON with a friendly error if the ingest file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Missing ingestion file: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_markdown(path: Path, markdown: str) -> None:
    """Write Markdown output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    """Normalize optional parser output into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean(value: Any, default: str = "Not available from extracted source") -> str:
    """Convert values into display-ready text."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value)


def _struct_lookup(structs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index extracted structs by Go struct name."""
    return {struct.get("name", ""): struct for struct in structs if struct.get("name")}


def _strip_go_type(go_type: str) -> str:
    """Extract a likely struct name from Go types like []Company or *Company."""
    cleaned = go_type.replace("[]", "").replace("*", "").strip()
    if "." in cleaned:
        cleaned = cleaned.rsplit(".", 1)[-1]
    return cleaned


def _resolve_struct_names(names: list[Any], lookup: dict[str, dict[str, Any]], max_depth: int = 1) -> list[dict[str, Any]]:
    """Resolve struct names and lightly include nested structs referenced by fields."""
    resolved: list[dict[str, Any]] = []
    queue: list[tuple[str, int]] = [(_clean(name, ""), 0) for name in names]
    seen: set[str] = set()

    while queue:
        name, depth = queue.pop(0)
        if not name or name in seen or name not in lookup:
            continue

        seen.add(name)
        struct = lookup[name]
        resolved.append(struct)

        if depth >= max_depth:
            continue

        for field in struct.get("fields", []):
            nested_name = _strip_go_type(_clean(field.get("type"), ""))
            if nested_name in lookup and nested_name not in seen:
                queue.append((nested_name, depth + 1))

    return resolved


def _infer_response_names(endpoint: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> list[str]:
    """Infer common response structs when the ingestor only captured request structs."""
    explicit = [str(name) for name in _as_list(endpoint.get("response_structs")) if name]
    if explicit:
        return explicit

    candidates: list[str] = []
    for request_name in _as_list(endpoint.get("request_structs")):
        request_name = _clean(request_name, "")
        if request_name.endswith("Request"):
            candidates.append(f"{request_name[:-7]}Response")

    controller = _clean(endpoint.get("controller"), "")
    if controller.endswith("Controller"):
        candidates.append(f"{controller[:-10]}Response")

    seen: set[str] = set()
    return [name for name in candidates if name in lookup and not (name in seen or seen.add(name))]


def _flatten_fields(structs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten struct fields and keep the owning struct for docs and drift checks."""
    fields: list[dict[str, Any]] = []

    for struct in structs:
        struct_name = _clean(struct.get("name"), "")
        for field in struct.get("fields", []):
            fields.append(
                {
                    "struct": struct_name,
                    "name": field.get("name", ""),
                    "type": field.get("type", ""),
                    "json": field.get("json", ""),
                    "form": field.get("form", ""),
                    "binding": field.get("binding", ""),
                    "raw_tag": field.get("raw_tag", ""),
                }
            )

    return fields


def _enrich_endpoint(endpoint: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attach request and response struct details to one endpoint."""
    request_names = [str(name) for name in _as_list(endpoint.get("request_structs")) if name]
    response_names = _infer_response_names(endpoint, lookup)
    request_structs = _resolve_struct_names(request_names, lookup, max_depth=1)
    response_structs = _resolve_struct_names(response_names, lookup, max_depth=2)

    enriched = dict(endpoint)
    enriched["request_struct_names"] = request_names
    enriched["response_struct_names"] = response_names
    enriched["request_structs"] = request_structs or request_names
    enriched["response_structs"] = response_structs or response_names
    enriched["request_fields"] = _flatten_fields(request_structs)
    enriched["response_fields"] = _flatten_fields(response_structs)
    return enriched


def _field_name(field: dict[str, Any]) -> str:
    """Pick the most API-facing field name available."""
    return _clean(field.get("json") or field.get("form") or field.get("name"), "")


def _list_text(value: Any) -> list[str]:
    """Normalize model output into a clean list of strings."""
    if isinstance(value, list):
        return [_clean(item, "") for item in value if _clean(item, "")]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _example_value(name: str) -> str:
    """Provide stable demo values for curl generation."""
    lowered = name.lower()
    if "gst" in lowered:
        return "27ABCDE1234F1Z5"
    if lowered in {"ak", "token"}:
        return "demo-ak"
    if "emp" in lowered:
        return "12345"
    if "glid" in lowered:
        return "987654"
    if "mobile" in lowered:
        return "9999999999"
    if "email" in lowered:
        return "demo@example.com"
    if "lat" in lowered:
        return "28.6139"
    if "lng" in lowered or "long" in lowered:
        return "77.2090"
    if "records" in lowered:
        return "10"
    return "demo"


def _build_sample_curl(endpoint: dict[str, Any]) -> str:
    """Generate a deterministic curl fallback from path, method, and query params."""
    method = _clean(endpoint.get("method"), "GET").upper()
    path = _clean(endpoint.get("path"), "")
    params = {str(param): _example_value(str(param)) for param in _as_list(endpoint.get("query_params"))}
    query = f"?{urlencode(params)}" if params else ""
    return f"curl -X {method} 'http://localhost:8080{path}{query}'"


def _schema_summary(endpoint: dict[str, Any]) -> str:
    """Build a compact OpenAPI-style fallback summary."""
    query_params = ", ".join(str(param) for param in _as_list(endpoint.get("query_params"))) or "none"
    request_models = ", ".join(endpoint.get("request_struct_names", [])) or "none"
    response_models = ", ".join(endpoint.get("response_struct_names", [])) or "none"

    return (
        f"method: {_clean(endpoint.get('method'))}\n"
        f"path: {_clean(endpoint.get('path'))}\n"
        f"query_params: [{query_params}]\n"
        f"request_models: [{request_models}]\n"
        f"response_models: [{response_models}]"
    )


def _fallback_sections(endpoint: dict[str, Any]) -> dict[str, Any]:
    """Create useful documentation if the AI call fails or returns partial JSON."""
    required_fields = [
        f"{field.get('struct')}.{_field_name(field)} is required"
        for field in endpoint.get("request_fields", [])
        if "required" in _clean(field.get("binding"), "").lower()
    ]
    validation_notes = required_fields or ["Not available from extracted source"]

    comments = _clean(endpoint.get("comments"))
    edge_cases = ["Empty or missing response data should be handled by API consumers."]
    if "stale" in comments.lower() or "incomplete" in comments.lower():
        edge_cases.append("Existing comments appear stale or incomplete and should be checked for drift.")

    return {
        "endpoint_summary": comments,
        "business_summary": comments,
        "request_explanation": "Request metadata is derived from extracted query parameters and Go request structs.",
        "response_explanation": "Response metadata is derived from inferred Go response structs when available.",
        "validation_notes": validation_notes,
        "sample_curl": _build_sample_curl(endpoint),
        "edge_cases": edge_cases,
        "openapi_schema_summary": _schema_summary(endpoint),
    }


def _build_structured_prompt(endpoint: dict[str, Any]) -> str:
    """Ask the model for a predictable JSON object that we can render later."""
    return (
        build_doc_prompt(endpoint)
        + """

Return only valid JSON with this exact shape:
{
  "endpoint_summary": "short technical summary",
  "business_summary": "business workflow summary",
  "request_explanation": "request fields and query params explanation",
  "response_explanation": "response fields explanation",
  "validation_notes": ["validation rule or Not available from extracted source"],
  "sample_curl": "curl command using visible method/path/query params only",
  "edge_cases": ["edge case grounded in extracted metadata"],
  "openapi_schema_summary": "compact OpenAPI-style schema notes"
}
"""
    )


def _normalize_sections(ai_payload: dict[str, Any], endpoint: dict[str, Any]) -> dict[str, Any]:
    """Merge AI output with deterministic fallbacks."""
    sections = _fallback_sections(endpoint)

    for key in DOC_KEYS:
        if key not in ai_payload or ai_payload.get(key) in (None, "", []):
            continue
        if key in {"validation_notes", "edge_cases"}:
            sections[key] = _list_text(ai_payload.get(key)) or sections[key]
        else:
            sections[key] = _clean(ai_payload.get(key))

    if ai_payload.get("error"):
        sections["generation_status"] = "fallback"
        sections["generation_error"] = ai_payload.get("error")
    else:
        sections["generation_status"] = "ai"
        sections["generation_error"] = ""

    return sections


def _field_table(fields: list[dict[str, Any]]) -> str:
    """Render request/response fields as a Markdown table."""
    if not fields:
        return "_Not available from extracted source_"

    lines = [
        "| Struct | Field | JSON/Form | Type | Binding |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in fields:
        json_or_form = field.get("json") or field.get("form") or ""
        lines.append(
            "| {struct} | {name} | {json_or_form} | {type} | {binding} |".format(
                struct=_clean(field.get("struct"), ""),
                name=_clean(field.get("name"), ""),
                json_or_form=_clean(json_or_form, ""),
                type=_clean(field.get("type"), ""),
                binding=_clean(field.get("binding"), ""),
            )
        )

    return "\n".join(lines)


def _bullet_list(items: list[str]) -> str:
    """Render a Markdown bullet list."""
    return "\n".join(f"- {item}" for item in items if item) or "- Not available from extracted source"


def _render_endpoint_markdown(doc: dict[str, Any]) -> str:
    """Render one endpoint's structured documentation into professional Markdown."""
    sections = doc["ai_sections"]
    query_params = ", ".join(doc.get("query_params", [])) or "None detected"

    return f"""## {doc['method']} {doc['path']}

| Field | Value |
| --- | --- |
| Controller | `{doc.get('controller', '')}` |
| Confidence | `{doc.get('confidence', 'Not available')}` |
| Source file | `{doc.get('source_file', '')}` |
| Query params | `{query_params}` |

### Summary
{sections['endpoint_summary']}

### Business Context
{sections['business_summary']}

### Request
{sections['request_explanation']}

#### Request Fields
{_field_table(doc.get('request_fields', []))}

### Response
{sections['response_explanation']}

#### Response Fields
{_field_table(doc.get('response_fields', []))}

### Validation Notes
{_bullet_list(_list_text(sections.get('validation_notes')))}

### Edge Cases
{_bullet_list(_list_text(sections.get('edge_cases')))}

### Sample curl
```bash
{sections['sample_curl']}
```

### OpenAPI-Style Schema Summary
```yaml
{sections['openapi_schema_summary']}
```
"""


def _render_full_markdown(payload: dict[str, Any]) -> str:
    """Render the full Markdown document."""
    metadata = payload["metadata"]
    endpoint_docs = "\n\n".join(_render_endpoint_markdown(doc) for doc in payload["endpoints"])

    return f"""# API DocAgent Generated API Documentation

Generated at: `{metadata['generated_at']}`  
Source repo: `{metadata['source_repo']}`  
Generated endpoints: `{metadata['generated_endpoints']}`  
Skipped endpoints: `{metadata['skipped_endpoints']}`

{endpoint_docs}
"""


def generate_docs(ingest: dict[str, Any], progress_callback=None) -> dict[str, Any]:
    """Generate structured docs for all valid endpoints.

    progress_callback(current, total, path) is called after each endpoint if provided.
    """
    structs = ingest.get("structs", [])
    lookup = _struct_lookup(structs)
    generated: list[dict[str, Any]] = []
    skipped = 0

    all_endpoints = ingest.get("endpoints", [])
    valid_endpoints = [ep for ep in all_endpoints if _clean(ep.get("path") or ep.get("route"), "")]
    total = len(valid_endpoints)

    for idx, endpoint in enumerate(all_endpoints):
        path = _clean(endpoint.get("path") or endpoint.get("route"), "")
        if not path:
            skipped += 1
            logger.warning("Skipping endpoint with missing route path: %s", endpoint)
            continue

        enriched = _enrich_endpoint(endpoint, lookup)
        logger.info("Generating docs for %s %s", _clean(enriched.get("method"), "GET"), path)

        ai_payload = generate_json(_build_structured_prompt(enriched))
        ai_sections = _normalize_sections(ai_payload, enriched)

        generated.append(
            {
                "path": path,
                "method": _clean(enriched.get("method"), "GET").upper(),
                "controller": enriched.get("controller", ""),
                "source_file": enriched.get("source_file", ""),
                "confidence": enriched.get("confidence", 0),
                "query_params": _as_list(enriched.get("query_params")),
                "request_structs": enriched.get("request_struct_names", []),
                "response_structs": enriched.get("response_struct_names", []),
                "request_fields": enriched.get("request_fields", []),
                "response_fields": enriched.get("response_fields", []),
                "comments": enriched.get("comments", ""),
                "ai_sections": ai_sections,
            }
        )

        if progress_callback is not None:
            progress_callback(len(generated), total, path)

    metadata = ingest.get("metadata", {})
    return {
        "metadata": {
            "project": metadata.get("project", "API DocAgent"),
            "source_repo": metadata.get("source_repo", "sample_api_go"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_total_endpoints": metadata.get("total_endpoints", len(ingest.get("endpoints", []))),
            "input_total_structs": metadata.get("total_structs", len(structs)),
            "generated_endpoints": len(generated),
            "skipped_endpoints": skipped,
        },
        "endpoints": generated,
    }


def main() -> None:
    """Run the documentation generator."""
    repo_root = _repo_root()
    output_dir = repo_root / "output"
    ingest_path = output_dir / "ingest.json"
    json_output_path = output_dir / "generated_docs.json"
    markdown_output_path = output_dir / "generated_docs.md"

    logger.info("Loading ingestion metadata from %s", ingest_path)
    ingest = _load_json(ingest_path)
    payload = generate_docs(ingest)
    markdown = _render_full_markdown(payload)

    _write_json(json_output_path, payload)
    _write_markdown(markdown_output_path, markdown)

    logger.info("Endpoints generated: %s", payload["metadata"]["generated_endpoints"])
    logger.info("Endpoints skipped: %s", payload["metadata"]["skipped_endpoints"])
    logger.info("JSON output: %s", json_output_path)
    logger.info("Markdown output: %s", markdown_output_path)


if __name__ == "__main__":
    main()
