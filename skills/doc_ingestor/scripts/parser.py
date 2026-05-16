"""Lightweight Go API metadata parser for API DocAgent.

This parser intentionally uses regex and string scanning instead of AST or
Tree-sitter. It is designed for hackathon-speed discovery on the sample Go
service, not for complete Go language coverage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .fastapi_parser import parse_fastapi_project, scan_python_files
except ImportError:
    from fastapi_parser import parse_fastapi_project, scan_python_files


IGNORED_DIRS = {"vendor", ".git", "cachefiles"}
IGNORED_FILES = {"go.sum"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}

GROUP_RE = re.compile(r'(?P<var>\w+)\s*:=\s*\w+\.Group\("(?P<prefix>[^"]+)"\)')
ROUTE_RE = re.compile(
    r'(?P<receiver>\w+)\.(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)'
    r'\(\s*"(?P<path>[^"]+)"\s*,\s*(?P<handler>[A-Za-z_][\w\.]*)',
)
FUNC_RE = re.compile(r"^\s*func\s+(?P<name>[A-Za-z_]\w*)\s*\(", re.MULTILINE)
STRUCT_RE = re.compile(r"type\s+(?P<name>[A-Za-z_]\w*)\s+struct\s*\{(?P<body>.*?)\}", re.DOTALL)
FIELD_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_]\w*)\s+"
    r"(?P<type>(?:\[\])?(?:\*?[\w\.]+|map\[[^\]]+\][\w\.]+))"
    r"(?:\s+`(?P<tags>[^`]*)`)?",
)
TAG_RE = re.compile(r'(?P<key>\w+):"(?P<value>[^"]*)"')
VAR_STRUCT_RE = re.compile(r"\bvar\s+\w+\s+structures\.(?P<struct>[A-Za-z_]\w*)")
INLINE_STRUCT_RE = re.compile(r"\bstructures\.(?P<struct>[A-Za-z_]\w*)\s*\{")
QUERY_CALL_RE = re.compile(r'\bc\.(?:Query|DefaultQuery|GetQuery)\(\s*"(?P<param>[^"]+)"')


def scan_go_files(project_root: str | Path) -> list[Path]:
    """Return all Go files below project_root, skipping noisy generated/runtime dirs."""
    root = Path(project_root)
    if not root.exists():
        return []

    files: list[Path] = []
    for path in root.rglob("*.go"):
        if path.name in IGNORED_FILES:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def scan_source_files(project_root: str | Path) -> list[Path]:
    """Return relevant Go or Python source files below a project root."""
    root = Path(project_root)
    if not root.exists():
        return []

    go_files = scan_go_files(root)
    py_files = scan_python_files(root)
    return sorted(go_files + py_files)


def read_file(path: Path) -> str:
    """Read a source file safely."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")
    except OSError:
        return ""


def parse_tag_values(tag_text: str | None) -> dict[str, str]:
    """Parse a Go struct tag into a flat dict such as {'json': 'id', 'form': 'id'}."""
    if not tag_text:
        return {}
    return {match.group("key"): match.group("value") for match in TAG_RE.finditer(tag_text)}


def clean_tag_value(value: str | None) -> str:
    """Drop tag options, preserving only the public field name."""
    if not value:
        return ""
    return value.split(",", 1)[0]


def parse_structs(go_files: list[Path], project_root: str | Path) -> list[dict[str, Any]]:
    """Extract Go struct names and field metadata."""
    root = Path(project_root)
    structs: list[dict[str, Any]] = []

    for path in go_files:
        source = read_file(path)
        for struct_match in STRUCT_RE.finditer(source):
            fields: list[dict[str, str]] = []
            body = struct_match.group("body")

            for line in body.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("//"):
                    continue

                field_match = FIELD_RE.match(line)
                if not field_match:
                    continue

                tags = parse_tag_values(field_match.group("tags"))
                fields.append(
                    {
                        "name": field_match.group("name"),
                        "type": field_match.group("type").strip(),
                        "json": clean_tag_value(tags.get("json")),
                        "form": clean_tag_value(tags.get("form")),
                        "binding": tags.get("binding", ""),
                        "raw_tag": field_match.group("tags") or "",
                    }
                )

            structs.append(
                {
                    "name": struct_match.group("name"),
                    "fields": fields,
                    "source_file": relative_path(path, root),
                }
            )

    return structs


def parse_handler_comments(go_files: list[Path], project_root: str | Path) -> dict[str, dict[str, str]]:
    """Collect contiguous // comments immediately above handler functions."""
    root = Path(project_root)
    handlers: dict[str, dict[str, str]] = {}

    for path in go_files:
        source = read_file(path)
        lines = source.splitlines()
        byte_offsets = line_start_offsets(source)

        for func_match in FUNC_RE.finditer(source):
            line_index = offset_to_line_index(byte_offsets, func_match.start())
            comment_lines: list[str] = []
            cursor = line_index - 1

            while cursor >= 0:
                stripped = lines[cursor].strip()
                if stripped.startswith("//"):
                    comment_lines.append(stripped[2:].strip())
                    cursor -= 1
                    continue
                if stripped == "":
                    cursor -= 1
                    continue
                break

            comment_lines.reverse()
            function_source = extract_function_source(source, func_match.start())
            struct_refs = sorted(set(VAR_STRUCT_RE.findall(function_source) + INLINE_STRUCT_RE.findall(function_source)))
            direct_query_params = sorted(set(QUERY_CALL_RE.findall(function_source)))

            handlers[func_match.group("name")] = {
                "comments": "\n".join(comment_lines),
                "source_file": relative_path(path, root),
                "request_structs": struct_refs,
                "direct_query_params": direct_query_params,
            }

    return handlers


def parse_routes(go_files: list[Path], project_root: str | Path) -> list[dict[str, str]]:
    """Extract Gin-style route definitions and resolve simple route group prefixes."""
    root = Path(project_root)
    endpoints: list[dict[str, str]] = []

    for path in go_files:
        source = read_file(path)
        groups = {match.group("var"): match.group("prefix") for match in GROUP_RE.finditer(source)}

        for route_match in ROUTE_RE.finditer(source):
            receiver = route_match.group("receiver")
            prefix = groups.get(receiver, "")
            raw_path = route_match.group("path")
            handler = route_match.group("handler").split(".")[-1]
            method = route_match.group("method")

            if method not in HTTP_METHODS:
                continue

            endpoints.append(
                {
                    "path": join_paths(prefix, raw_path),
                    "method": method,
                    "controller": handler,
                    "comments": "",
                    "query_params": [],
                    "source_file": relative_path(path, root),
                }
            )

    return endpoints


def enrich_endpoints(
    endpoints: list[dict[str, Any]],
    handlers: dict[str, dict[str, Any]],
    structs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach handler comments and visible query params to route metadata."""
    structs_by_name = {item["name"]: item for item in structs}
    enriched: list[dict[str, Any]] = []

    for endpoint in endpoints:
        item = dict(endpoint)
        handler_meta = handlers.get(item["controller"], {})
        request_struct_names = handler_meta.get("request_structs", [])
        query_params = set(handler_meta.get("direct_query_params", []))

        for struct_name in request_struct_names:
            for field in structs_by_name.get(struct_name, {}).get("fields", []):
                form_name = field.get("form", "")
                if form_name and form_name != "-":
                    query_params.add(form_name)

        item["comments"] = handler_meta.get("comments", "")
        item["query_params"] = sorted(query_params)
        if handler_meta.get("source_file"):
            item["source_file"] = handler_meta["source_file"]
        if request_struct_names:
            item["request_structs"] = request_struct_names

        enriched.append(item)

    return enriched


def parse_project(project_root: str | Path = "sample_api_go") -> dict[str, list[dict[str, Any]]]:
    """Parse a Go or FastAPI project and return route and struct metadata."""
    root = Path(project_root)

    go_files = scan_go_files(root)
    py_files = scan_python_files(root)

    if py_files and not go_files:
        return parse_fastapi_project(root)

    structs = parse_structs(go_files, root)
    handlers = parse_handler_comments(go_files, root)
    endpoints = parse_routes(go_files, root)

    return {
        "endpoints": enrich_endpoints(endpoints, handlers, structs),
        "structs": structs,
    }


def join_paths(prefix: str, path: str) -> str:
    """Join Gin group prefixes and route paths without double slashes."""
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def relative_path(path: Path, root: Path) -> str:
    """Return a stable relative path when possible."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def line_start_offsets(source: str) -> list[int]:
    """Build byte offsets for line lookup."""
    offsets = [0]
    for match in re.finditer(r"\n", source):
        offsets.append(match.end())
    return offsets


def offset_to_line_index(offsets: list[int], offset: int) -> int:
    """Convert a source offset to a zero-based line index."""
    line_index = 0
    for idx, start in enumerate(offsets):
        if start > offset:
            break
        line_index = idx
    return line_index


def extract_function_source(source: str, start: int) -> str:
    """Return a best-effort function body by balancing braces."""
    open_brace = source.find("{", start)
    if open_brace == -1:
        return ""

    depth = 0
    for idx in range(open_brace, len(source)):
        char = source[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    return source[start:]


def main() -> None:
    """CLI helper for quick local verification."""
    import argparse

    parser = argparse.ArgumentParser(description="Parse Go API metadata.")
    parser.add_argument("project_root", nargs="?", default="sample_api_go")
    args = parser.parse_args()

    print(json.dumps(parse_project(args.project_root), indent=2))


if __name__ == "__main__":
    main()
