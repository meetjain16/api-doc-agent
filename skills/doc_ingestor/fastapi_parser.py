"""FastAPI metadata parser for API DocAgent.

This parser uses the Python AST to extract route decorators, query/path/body
parameters, and Pydantic model fields from FastAPI-style projects.

Fixes over the original:
- Two-pass model collection: all BaseModel subclasses are gathered globally
  before route parsing, so cross-file imports are resolved correctly.
- Depends/Security injection params are skipped (not query params).
- APIRouter(prefix=...) is detected and prepended to route paths.
- ast.AsyncFunctionDef routes are handled (FastAPI async def handlers).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


IGNORED_DIRS = {"vendor", ".git", "cachefiles", "__pycache__", ".venv", "venv", "output"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
BASE_MODEL_NAMES = {"BaseModel", "pydantic.BaseModel"}
DEPENDENCY_KINDS = {"Depends", "Security"}
FASTAPI_INTERNALS = {"Request", "Response", "BackgroundTasks", "HTTPConnection", "WebSocket"}


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")
    except OSError:
        return ""


def scan_python_files(project_root: str | Path) -> list[Path]:
    root = Path(project_root)
    if not root.exists():
        return []

    files: list[Path] = []
    for path in root.rglob("*.py"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            continue
        if path.name.startswith("test_"):
            continue
        files.append(path)
    return sorted(files)


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _name_from_expr(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name_from_expr(node.value)}.{node.attr}".strip(".")
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _call_name(node: ast.AST | None) -> str:
    if not isinstance(node, ast.Call):
        return ""
    return _name_from_expr(node.func)


def _is_base_model(class_node: ast.ClassDef) -> bool:
    for base in class_node.bases:
        base_name = _name_from_expr(base)
        if base_name in BASE_MODEL_NAMES or base_name.endswith(".BaseModel"):
            return True
    return False


def _extract_comment_and_docstring(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    doc = ast.get_docstring(func_node) or ""
    return doc.strip()


def _extract_model_fields(class_node: ast.ClassDef) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []

    for stmt in class_node.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue

        field_name = stmt.target.id
        field_type = _name_from_expr(stmt.annotation)
        binding = ""
        raw_tag = ""
        alias = ""

        if isinstance(stmt.value, ast.Call):
            try:
                raw_tag = ast.unparse(stmt.value)
            except Exception:
                raw_tag = ""
            for kw in stmt.value.keywords:
                if kw.arg == "alias":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        alias = kw.value.value
                    else:
                        alias = _name_from_expr(kw.value)
                if kw.arg == "default":
                    binding = "default"

        fields.append(
            {
                "name": field_name,
                "type": field_type,
                "json": alias or field_name,
                "form": alias or field_name,
                "binding": binding,
                "raw_tag": raw_tag,
            }
        )

    return fields


def _extract_router_prefixes(tree: ast.Module) -> dict[str, str]:
    """Find APIRouter(prefix=...) assignments and return {var_name: prefix}."""
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if _call_name(node.value) not in {"APIRouter", "fastapi.APIRouter"}:
            continue
        prefix = ""
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = kw.value.value
                break
        if prefix:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prefixes[target.id] = prefix
    return prefixes


def _route_info(
    dec: ast.expr,
    router_prefixes: dict[str, str] | None = None,
) -> tuple[str, str, dict[str, Any]] | None:
    if not isinstance(dec, ast.Call):
        return None

    func_name = _name_from_expr(dec.func)
    parts = func_name.rsplit(".", 1)
    method = parts[-1].upper()
    receiver = parts[0] if len(parts) > 1 else ""

    if method not in HTTP_METHODS:
        return None

    route_path = ""
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        route_path = dec.args[0].value

    prefix = (router_prefixes or {}).get(receiver, "")
    if prefix:
        route_path = f"{prefix.rstrip('/')}/{route_path.lstrip('/')}"

    kwargs = {kw.arg: kw.value for kw in dec.keywords if kw.arg}
    response_model = _name_from_expr(kwargs.get("response_model"))
    tags: list[str] = []
    if "tags" in kwargs:
        tags_node = kwargs["tags"]
        if isinstance(tags_node, (ast.List, ast.Tuple)):
            tags = [
                item.value
                for item in tags_node.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            ]

    return method, route_path, {"response_model": response_model, "tags": tags}


def _default_kind(default: ast.expr | None) -> str:
    if default is None:
        return ""
    return _call_name(default).rsplit(".", 1)[-1]


def _path_params(route_path: str) -> list[str]:
    return re.findall(r"\{([^}]+)\}", route_path)


def _extract_signature_params(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    model_names: set[str],
    route_path: str,
) -> tuple[list[str], list[str]]:
    query_params: list[str] = []
    request_structs: list[str] = []
    path_param_names = set(_path_params(route_path))

    positional = list(function_node.args.args)
    defaults = (
        [None] * (len(positional) - len(function_node.args.defaults))
        + list(function_node.args.defaults)
    )

    for arg, default in zip(positional, defaults):
        if arg.arg in {"self", "cls"}:
            continue

        annotation = _name_from_expr(arg.annotation)
        default_kind = _default_kind(default)

        # Skip FastAPI dependency injection
        if default_kind in DEPENDENCY_KINDS:
            continue

        # Skip path params
        if arg.arg in path_param_names or default_kind == "Path":
            continue

        # Explicit query params
        if default_kind in {"Query", "DefaultQuery"} or annotation.endswith("Query"):
            query_params.append(arg.arg)
            continue

        # Explicit body/form/file params
        if default_kind in {"Body", "Form", "File"}:
            base = annotation.split("[")[0].rsplit(".", 1)[-1]
            if base in model_names:
                request_structs.append(base)
            continue

        # Skip common FastAPI framework types
        base_annotation = annotation.split("[")[0].rsplit(".", 1)[-1]
        if base_annotation in FASTAPI_INTERNALS:
            continue

        # Type annotation resolves to a known Pydantic model
        if base_annotation in model_names:
            request_structs.append(base_annotation)
            continue

        query_params.append(arg.arg)

    return sorted(set(query_params)), sorted(set(request_structs))


def parse_fastapi_project(project_root: str | Path) -> dict[str, list[dict[str, Any]]]:
    root = Path(project_root)
    py_files = scan_python_files(root)

    # Pass 1: collect ALL Pydantic BaseModel subclasses across the entire project.
    # This resolves cross-file imports (e.g. models defined in schemas.py and used in routes.py).
    all_models: dict[str, dict[str, Any]] = {}
    for path in py_files:
        source = read_file(path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and _is_base_model(node):
                all_models[node.name] = {
                    "name": node.name,
                    "fields": _extract_model_fields(node),
                    "source_file": relative_path(path, root),
                }

    model_names = set(all_models.keys())
    structs = list(all_models.values())
    endpoints: list[dict[str, Any]] = []

    # Pass 2: collect routes using the global model registry.
    for path in py_files:
        source = read_file(path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        router_prefixes = _extract_router_prefixes(tree)

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            route_meta = None
            for dec in node.decorator_list:
                route_meta = _route_info(dec, router_prefixes)
                if route_meta:
                    break

            if not route_meta:
                continue

            method, route_path, extras = route_meta
            query_params, request_structs = _extract_signature_params(node, model_names, route_path)
            response_model = extras.get("response_model", "")

            endpoints.append(
                {
                    "path": route_path,
                    "method": method,
                    "controller": node.name,
                    "comments": _extract_comment_and_docstring(node),
                    "query_params": query_params,
                    "source_file": relative_path(path, root),
                    "request_structs": request_structs,
                    "response_structs": [response_model] if response_model else [],
                    "path_params": _path_params(route_path),
                    "tags": extras.get("tags", []),
                }
            )

    return {"endpoints": endpoints, "structs": structs}
