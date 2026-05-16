"""Prompt templates for API DocAgent documentation generation.

The functions in this module convert extracted Go endpoint metadata into
source-grounded prompts for the OpenAI client wrapper.
"""

from __future__ import annotations

import json
from typing import Any


MISSING_VALUE = "Not available from extracted source"


def _clean_text(value: Any) -> str:
    """Convert optional metadata values into readable prompt text."""
    if value is None:
        return MISSING_VALUE

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or MISSING_VALUE

    return str(value)


def _as_list(value: Any) -> list[Any]:
    """Normalize parser output that may be missing, scalar, or already a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _format_field(field: Any) -> str:
    """Format one struct/query field while preserving unknown keys."""
    if isinstance(field, str):
        return f"- {field}"

    if not isinstance(field, dict):
        return f"- {_clean_text(field)}"

    name = _clean_text(field.get("name") or field.get("field") or field.get("param"))
    field_type = _clean_text(field.get("type") or field.get("go_type"))
    json_name = _clean_text(field.get("json") or field.get("json_name"))
    required = field.get("required")
    comment = _clean_text(field.get("comment") or field.get("description"))

    parts = [name]
    if field_type != MISSING_VALUE:
        parts.append(f"type={field_type}")
    if json_name != MISSING_VALUE:
        parts.append(f"json={json_name}")
    if required is not None:
        parts.append(f"required={required}")
    if comment != MISSING_VALUE:
        parts.append(f"notes={comment}")

    extra_keys = sorted(
        key
        for key in field
        if key not in {"name", "field", "param", "type", "go_type", "json", "json_name", "required", "comment", "description"}
    )
    if extra_keys:
        extras = ", ".join(f"{key}={field[key]}" for key in extra_keys)
        parts.append(f"extra={extras}")

    return f"- {'; '.join(parts)}"


def _format_fields(fields: Any) -> str:
    """Format a list of struct fields or query parameters."""
    formatted = [_format_field(field) for field in _as_list(fields)]
    return "\n".join(formatted) if formatted else f"- {MISSING_VALUE}"


def _format_struct(struct: Any) -> str:
    """Format one extracted Go struct for prompt context."""
    if isinstance(struct, str):
        return f"Struct: {struct}\nFields:\n- {MISSING_VALUE}"

    if not isinstance(struct, dict):
        return f"Struct: {_clean_text(struct)}\nFields:\n- {MISSING_VALUE}"

    name = _clean_text(struct.get("name") or struct.get("struct_name"))
    source_file = _clean_text(struct.get("source_file") or struct.get("file"))
    fields = _format_fields(struct.get("fields"))

    return f"Struct: {name}\nSource file: {source_file}\nFields:\n{fields}"


def _collect_structs(endpoint: dict[str, Any]) -> list[Any]:
    """Collect likely request/response structs from flexible ingestion shapes."""
    struct_keys = (
        "request_struct",
        "request_structs",
        "request_schema",
        "response_struct",
        "response_structs",
        "response_schema",
        "structs",
    )

    structs: list[Any] = []
    for key in struct_keys:
        structs.extend(_as_list(endpoint.get(key)))

    seen: set[str] = set()
    unique_structs: list[Any] = []
    for struct in structs:
        if isinstance(struct, dict):
            identity = _clean_text(struct.get("name") or struct.get("struct_name") or json.dumps(struct, sort_keys=True))
        else:
            identity = _clean_text(struct)

        if identity in seen:
            continue
        seen.add(identity)
        unique_structs.append(struct)

    return unique_structs


def _format_query_params(endpoint: dict[str, Any]) -> str:
    """Format query params from endpoint-level metadata."""
    query_params = endpoint.get("query_params") or endpoint.get("filters") or endpoint.get("params")
    return _format_fields(query_params)


def format_endpoint_metadata(endpoint: dict[str, Any]) -> str:
    """Create compact, source-grounded context for prompt templates."""
    method = _clean_text(endpoint.get("method"))
    path = _clean_text(endpoint.get("path") or endpoint.get("route"))
    controller = _clean_text(endpoint.get("controller") or endpoint.get("handler"))
    comments = _clean_text(endpoint.get("comments") or endpoint.get("comment"))
    source_file = _clean_text(endpoint.get("source_file") or endpoint.get("handler_file"))

    structs = _collect_structs(endpoint)
    formatted_structs = "\n\n".join(_format_struct(struct) for struct in structs)
    if not formatted_structs:
        formatted_structs = f"Structs:\n- {MISSING_VALUE}"

    return f"""Endpoint
- Method: {method}
- Path: {path}
- Controller: {controller}
- Handler source: {source_file}
- Existing comments: {comments}

Query parameters
{_format_query_params(endpoint)}

Extracted structs
{formatted_structs}

Raw endpoint metadata
```json
{json.dumps(endpoint, indent=2, sort_keys=True, default=str)}
```"""


def build_doc_prompt(endpoint: dict) -> str:
    """Build an enterprise-grade prompt for API documentation synthesis."""
    endpoint_context = format_endpoint_metadata(endpoint)

    return f"""You are API DocAgent, an internal engineering documentation assistant.

Generate concise, enterprise-grade API documentation from the extracted Go service metadata below.
Use only the provided metadata. If the source does not expose a field, validation rule, or business rule, write "Not available from extracted source" instead of guessing.

Documentation goals:
1. Endpoint summary: explain what this API does and its likely business workflow.
2. Request explanation: describe path, method, query parameters, and request struct fields.
3. Response explanation: describe response structs and business meaning of important fields.
4. Validation rules: list only explicit or strongly inferable validation constraints.
5. Edge cases: identify missing filters, empty responses, deprecated fields, stale docs, and schema drift risks when visible.
6. Sample curl request: use the actual HTTP method, path, and visible query parameters.
7. OpenAPI-style schema summary: provide a compact schema-oriented view of parameters and models.

Style:
- Audience: internal backend engineers and API platform reviewers.
- Tone: precise, practical, and business-aware.
- Keep sections short and scannable.
- Preserve original field names exactly.
- Do not invent authentication, headers, status codes, services, databases, or external integrations.

Extracted endpoint metadata:
{endpoint_context}
"""


def build_markdown_prompt(endpoint: dict) -> str:
    """Build a prompt that asks the model to emit final Markdown documentation."""
    endpoint_context = format_endpoint_metadata(endpoint)

    return f"""You are API DocAgent generating Markdown for an internal API catalog.

Create a Markdown document for this endpoint using the exact structure below:

# <METHOD> <PATH>

## Summary
Briefly explain the endpoint and business context.

## Request
- Method:
- Path:
- Controller:
- Query Parameters:
- Request Body / Structs:

## Response
Explain response fields, nested structs, deprecated fields, and any observed mismatch between docs and implementation.

## Validation Rules
List explicit rules first. Mark unavailable rules as "Not available from extracted source".

## Edge Cases
List realistic edge cases grounded in the extracted metadata.

## Sample curl
Provide one curl command using only visible path and query parameters.

## OpenAPI-Style Schema Summary
Provide concise YAML-like schema notes for parameters, request models, and response models.

Rules:
- Use only the extracted metadata.
- Do not hallucinate unknown fields, auth headers, status codes, or backend behavior.
- Preserve Go struct names, JSON field names, query parameter names, and controller names exactly.
- Keep the output concise enough for hackathon review but complete enough for drift detection.

Extracted endpoint metadata:
{endpoint_context}
"""
