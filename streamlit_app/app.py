"""Streamlit dashboard for the API DocAgent hackathon demo."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import streamlit as st

try:
    import yaml
except ImportError:
    yaml = None


PAGE_TITLE = "API DocAgent — AI-Powered API Intelligence Platform"


def repo_root() -> Path:
    """Return the API DocAgent repository root."""
    return Path(__file__).resolve().parents[1]


def output_dir() -> Path:
    """Return the generated artifact directory."""
    return repo_root() / "output"


def load_repos_config() -> list[dict[str, Any]]:
    """Load repo list from repos.yaml at the project root."""
    if yaml is None:
        return []
    config_path = repo_root() / "repos.yaml"
    if not config_path.exists():
        return []
    try:
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        return config.get("repos", []) if isinstance(config, dict) else []
    except Exception:
        return []


def repo_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@st.cache_resource(show_spinner=False)
def _get_runner() -> Any:
    """Load the pipeline runner module once and cache it for the session."""
    runner_path = repo_root() / "skills" / "pipeline" / "runner.py"
    spec = importlib.util.spec_from_file_location("_api_docagent_runner", runner_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_api_docagent_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


def artifact_paths(slug: str | None = None) -> dict[str, Path]:
    """Return artifact paths for the selected repo (or the default Go sample)."""
    out = output_dir()
    base = out / "repos" / slug if slug else out
    return {
        "ingest": base / "ingest.json",
        "generated_docs_json": base / "generated_docs.json",
        "generated_docs_md": base / "generated_docs.md",
        "breaking_changes_json": base / "breaking_changes.json",
        "breaking_changes_md": base / "breaking_changes.md",
    }


@st.cache_data(show_spinner=False)
def load_json(path_text: str) -> dict[str, Any]:
    """Load JSON safely for the dashboard."""
    path = Path(path_text)
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_load_error": f"Invalid JSON: {path}"}


@st.cache_data(show_spinner=False)
def load_text(path_text: str) -> str:
    """Load text/Markdown safely for the dashboard."""
    path = Path(path_text)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_artifacts(slug: str | None = None) -> dict[str, Any]:
    """Load all API DocAgent outputs for the given repo slug (or default Go sample)."""
    paths = artifact_paths(slug)
    return {
        "paths": paths,
        "ingest": load_json(str(paths["ingest"])),
        "generated_docs": load_json(str(paths["generated_docs_json"])),
        "generated_markdown": load_text(str(paths["generated_docs_md"])),
        "breaking_changes": load_json(str(paths["breaking_changes_json"])),
        "breaking_markdown": load_text(str(paths["breaking_changes_md"])),
    }


def configure_page() -> None:
    """Apply page settings and lightweight styling."""
    st.set_page_config(page_title=PAGE_TITLE, layout="wide", initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
        .stApp {
            background: #0f172a;
            color: #e5e7eb;
        }
        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3, h4, h5, h6,
        .stMarkdown, .stCaption, label {
            color: #e5e7eb;
        }
        .hero {
            border: 1px solid #334155;
            border-left: 6px solid #38bdf8;
            border-radius: 8px;
            padding: 1rem 1.2rem;
            background: #111827;
            margin-bottom: 1rem;
            box-shadow: 0 10px 30px rgba(2, 6, 23, .28);
        }
        .hero h1 {
            font-size: 2rem;
            margin: 0 0 .35rem 0;
            color: #f8fafc !important;
        }
        .hero p {
            margin: 0;
            color: #cbd5e1 !important;
        }
        div[data-testid="stMetric"] {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 8px 24px rgba(2, 6, 23, .22);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: #cbd5e1 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #f8fafc !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            color: #93c5fd !important;
        }
        .badge {
            display: inline-block;
            border-radius: 999px;
            padding: .18rem .55rem;
            font-size: .78rem;
            font-weight: 700;
            border: 1px solid transparent;
            line-height: 1.35;
            letter-spacing: 0;
        }
        .badge-high {
            background: #fee2e2;
            color: #7f1d1d !important;
            border-color: #ef4444;
        }
        .badge-medium {
            background: #ffedd5;
            color: #7c2d12 !important;
            border-color: #fb923c;
        }
        .badge-low {
            background: #dbeafe;
            color: #1e3a8a !important;
            border-color: #60a5fa;
        }
        .badge-none {
            background: #dcfce7;
            color: #14532d !important;
            border-color: #bbf7d0;
        }
        .pill {
            display: inline-block;
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            padding: .15rem .5rem;
            margin: .12rem .18rem .12rem 0;
            background: #ffffff;
            color: #334155;
            font-size: .82rem;
        }
        .pill, .pill * {
            color: #334155 !important;
        }
        .info-card {
            border: 1px solid #334155;
            border-radius: 8px;
            background: #111827;
            color: #e5e7eb !important;
            padding: .85rem 1rem;
            margin-bottom: .75rem;
            box-shadow: 0 8px 24px rgba(2, 6, 23, .18);
        }
        .info-card * {
            color: #e5e7eb !important;
        }
        .callout-high {
            border: 1px solid #fca5a5;
            border-left: 6px solid #dc2626;
            border-radius: 8px;
            background: #fff1f2;
            color: #7f1d1d !important;
            padding: .85rem 1rem;
            margin-bottom: .75rem;
            box-shadow: 0 8px 24px rgba(127, 29, 29, .16);
        }
        .callout-high * {
            color: #7f1d1d !important;
        }
        .callout-medium {
            border: 1px solid #fdba74;
            border-left: 6px solid #f97316;
            border-radius: 8px;
            background: #fff7ed;
            color: #7c2d12 !important;
            padding: .85rem 1rem;
            margin-bottom: .75rem;
            box-shadow: 0 8px 24px rgba(124, 45, 18, .14);
        }
        .callout-medium * {
            color: #7c2d12 !important;
        }
        .callout-low {
            border: 1px solid #93c5fd;
            border-left: 6px solid #3b82f6;
            border-radius: 8px;
            background: #eff6ff;
            color: #1e3a8a !important;
            padding: .85rem 1rem;
            margin-bottom: .75rem;
            box-shadow: 0 8px 24px rgba(30, 58, 138, .12);
        }
        .callout-low * {
            color: #1e3a8a !important;
        }
        div[data-testid="stExpander"] {
            border-color: #334155;
            background: #0b1220;
            border-radius: 8px;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {
            border-radius: 8px;
            overflow: hidden;
        }
        .muted {
            color: #94a3b8 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render product header."""
    st.markdown(
        f"""
        <div class="hero">
          <h1>{PAGE_TITLE}</h1>
          <p>Route discovery, schema extraction, AI documentation, and drift detection for Go services.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def artifact_status(paths: dict[str, Path]) -> list[str]:
    """Return missing artifact names."""
    return [name for name, path in paths.items() if not path.exists()]


def pipeline_commands() -> list[tuple[str, list[str]]]:
    """Return the dashboard-executable pipeline commands in order."""
    root = repo_root()
    python = sys.executable
    return [
        ("Step 1 — Parse Go source", [python, str(root / "skills" / "doc_ingestor" / "main.py")]),
        ("Step 2 — Generate AI docs", [python, str(root / "skills" / "doc_generator" / "main.py")]),
        ("Step 3 — Detect drift", [python, str(root / "skills" / "drift_detector" / "main.py")]),
    ]


def run_pipeline_command(label: str, command: list[str]) -> dict[str, Any]:
    """Run one pipeline command and return its execution details."""
    completed = subprocess.run(
        command,
        cwd=repo_root(),
        capture_output=True,
        text=True,
    )

    return {
        "label": label,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_pipeline_steps(step_indexes: list[int] | None = None) -> list[dict[str, Any]]:
    """Execute one or more pipeline steps and refresh cached artifacts."""
    commands = pipeline_commands()
    indexes = step_indexes if step_indexes is not None else list(range(len(commands)))
    results: list[dict[str, Any]] = []

    with st.spinner("Running pipeline..."):
        for index in indexes:
            label, command = commands[index]
            results.append(run_pipeline_command(label, command))

    load_json.clear()
    load_text.clear()
    st.session_state["pipeline_results"] = results
    st.rerun()


def render_pipeline_results() -> None:
    """Show the latest dashboard-triggered pipeline run."""
    results = st.session_state.get("pipeline_results", [])
    if not results:
        return

    st.sidebar.divider()
    st.sidebar.subheader("Latest Pipeline Run")
    for result in results:
        status = "OK" if result.get("returncode") == 0 else f"Exit {result.get('returncode')}"
        st.sidebar.caption(f"{result.get('label')}: {status}")

    with st.expander("Pipeline run details", expanded=False):
        for result in results:
            status = "OK" if result.get("returncode") == 0 else f"Exit {result.get('returncode')}"
            st.markdown(f"#### {result.get('label')} — {status}")
            st.code(" ".join(result.get("command", [])), language="bash")
            if result.get("stdout"):
                st.markdown("**Stdout**")
                st.code(result["stdout"], language="text")
            if result.get("stderr"):
                st.markdown("**Stderr**")
                st.code(result["stderr"], language="text")


def render_pipeline_controls(selected_repo: dict[str, Any] | None) -> None:
    """Render Run Pipeline button for the currently selected repo."""
    if not selected_repo:
        st.sidebar.caption("Select a configured repo above to run its pipeline.")
        if st.sidebar.button("Run Go sample (all steps)", use_container_width=True):
            run_pipeline_steps()
        return

    desc = selected_repo.get("description", "")
    if desc:
        st.sidebar.caption(desc)

    if st.sidebar.button("Run Pipeline", type="primary", use_container_width=True):
        with st.spinner(f"Running pipeline for {selected_repo['name']}..."):
            try:
                _get_runner.clear()  # force fresh module load on each run
                runner = _get_runner()
                result = runner.run_by_name(selected_repo["name"])
                if result.get("status") == "OK":
                    st.sidebar.success(
                        f"Done — {result.get('docs_generated', 0)} endpoints documented."
                    )
                    load_json.clear()
                    load_text.clear()
                    st.session_state["_active_slug"] = repo_slug(selected_repo["name"])
                    st.rerun()
                else:
                    st.sidebar.error(
                        f"Failed at {result.get('stage', '?')}: {result.get('error', 'unknown')}"
                    )
            except Exception as exc:
                st.sidebar.error(f"Pipeline error: {exc}")


def render_sidebar(repos: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Render sidebar navigation, repo selector, and pipeline runner. Returns (page, slug)."""
    st.sidebar.title("API DocAgent")

    # Repo selector
    selected_slug: str | None = st.session_state.get("_active_slug")
    selected_repo: dict[str, Any] | None = None

    if repos:
        options = ["[Sample Go Service]"] + [r["name"] for r in repos]
        default_idx = 0
        if selected_slug:
            for i, r in enumerate(repos):
                if repo_slug(r["name"]) == selected_slug:
                    default_idx = i + 1
                    break
        choice = st.sidebar.selectbox("Repository", options, index=default_idx)
        if choice != "[Sample Go Service]":
            selected_slug = repo_slug(choice)
            selected_repo = next((r for r in repos if r["name"] == choice), None)
        else:
            selected_slug = None
        st.session_state["_active_slug"] = selected_slug

    st.sidebar.subheader("Run Pipeline")
    render_pipeline_controls(selected_repo)

    page = st.sidebar.radio(
        "Navigate",
        [
            "Overview Dashboard",
            "API Explorer",
            "Generated Documentation Viewer",
            "Drift Detection Dashboard",
        ],
    )

    st.sidebar.divider()
    st.sidebar.subheader("Artifact Status")
    paths = artifact_paths(selected_slug)
    for name, path in paths.items():
        icon = "✓" if path.exists() else "○"
        st.sidebar.caption(f"{icon} {name}")

    return page, selected_slug


def as_list(value: Any) -> list[Any]:
    """Normalize optional values into lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value: Any, default: str = "Not available") -> str:
    """Convert optional values into readable text."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    return str(value)


def get_endpoints(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer generated docs endpoints; fall back to ingested endpoints."""
    generated = artifacts.get("generated_docs", {})
    ingest = artifacts.get("ingest", {})
    return generated.get("endpoints") or ingest.get("endpoints") or []


def endpoint_label(endpoint: dict[str, Any]) -> str:
    """Create a stable dropdown label."""
    return f"{clean_text(endpoint.get('method'), 'GET')} {clean_text(endpoint.get('path'), '')}"


def endpoint_rows(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build table rows for the API Explorer."""
    return [
        {
            "method": clean_text(endpoint.get("method"), ""),
            "path": clean_text(endpoint.get("path"), ""),
            "controller": clean_text(endpoint.get("controller"), ""),
            "confidence": endpoint.get("confidence", ""),
        }
        for endpoint in endpoints
    ]


def filter_endpoints(
    endpoints: list[dict[str, Any]],
    search: str,
    methods: list[str],
) -> list[dict[str, Any]]:
    """Filter endpoints by text and method."""
    search_norm = search.lower().strip()
    method_set = set(methods)
    filtered: list[dict[str, Any]] = []

    for endpoint in endpoints:
        method = clean_text(endpoint.get("method"), "")
        searchable = " ".join(
            [
                clean_text(endpoint.get("path"), ""),
                method,
                clean_text(endpoint.get("controller"), ""),
                " ".join(str(param) for param in as_list(endpoint.get("query_params"))),
            ]
        ).lower()

        if method_set and method not in method_set:
            continue
        if search_norm and search_norm not in searchable:
            continue

        filtered.append(endpoint)

    return filtered


def field_rows(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare struct fields for display."""
    return [
        {
            "struct": clean_text(field.get("struct"), ""),
            "field": clean_text(field.get("name"), ""),
            "json/form": clean_text(field.get("json") or field.get("form"), ""),
            "type": clean_text(field.get("type"), ""),
            "binding": clean_text(field.get("binding"), ""),
        }
        for field in fields
    ]


def render_pills(values: list[Any]) -> None:
    """Render compact badges for query params and fields."""
    if not values:
        st.caption("None detected")
        return

    html = "".join(f'<span class="pill">{clean_text(value)}</span>' for value in values)
    st.markdown(html, unsafe_allow_html=True)


def severity_badge(severity: str) -> str:
    """Return HTML severity badge."""
    normalized = severity.upper() if severity else "NONE"
    css = {
        "HIGH": "badge-high",
        "MEDIUM": "badge-medium",
        "LOW": "badge-low",
        "NONE": "badge-none",
    }.get(normalized, "badge-low")
    return f'<span class="badge {css}">{normalized}</span>'


def issue_type_group(issue_type: str) -> str:
    """Group comparator issue types into dashboard categories."""
    if issue_type == "REMOVED_FIELD":
        return "Removed Fields"
    if issue_type == "POSSIBLE_RENAMED_FIELD":
        return "Renamed Fields"
    if "UNDOCUMENTED" in issue_type:
        return "Undocumented Fields"
    return "Other Drift"


def all_issues(breaking_changes: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten drift issues and keep endpoint context."""
    flattened: list[dict[str, Any]] = []
    for result in breaking_changes.get("drift_results", []):
        for issue in result.get("issues", []):
            flattened.append(
                {
                    "endpoint": result.get("endpoint", ""),
                    "method": result.get("method", ""),
                    "endpoint_severity": result.get("severity", ""),
                    **issue,
                }
            )
    return flattened


def issue_rows(issues: list[dict[str, Any]], issue_types: set[str] | None = None) -> list[dict[str, Any]]:
    """Format drift issues for tables."""
    rows: list[dict[str, Any]] = []
    for issue in issues:
        if issue_types and issue.get("type") not in issue_types:
            continue
        rows.append(
            {
                "severity": issue.get("severity", ""),
                "type": issue.get("type", ""),
                "method": issue.get("method", ""),
                "endpoint": issue.get("endpoint", ""),
                "field": issue.get("field", ""),
                "suggested_replacement": issue.get("suggested_replacement", ""),
                "detail": issue.get("detail", ""),
            }
        )
    return rows


def render_missing_artifacts(missing: list[str]) -> None:
    """Show missing artifact guidance without stopping the app."""
    if not missing:
        return

    st.warning(
        "Some generated artifacts are missing. Run the ingestor, doc generator, and drift detector to unlock the full dashboard."
    )
    with st.expander("Missing artifact details"):
        for name in missing:
            st.write(f"- `{name}`")


def render_overview(artifacts: dict[str, Any]) -> None:
    """Render overview metrics."""
    ingest_meta = artifacts.get("ingest", {}).get("metadata", {})
    drift_meta = artifacts.get("breaking_changes", {}).get("metadata", {})
    generated_meta = artifacts.get("generated_docs", {}).get("metadata", {})

    total_apis = ingest_meta.get("total_endpoints") or generated_meta.get("generated_endpoints") or 0
    total_structs = ingest_meta.get("total_structs") or generated_meta.get("input_total_structs") or 0
    drift_issues = drift_meta.get("drift_issues_found", 0)
    high_issues = drift_meta.get("high_severity_issues", 0)

    st.subheader("Overview Dashboard")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total APIs Parsed", total_apis)
    col2.metric("Structs Extracted", total_structs)
    col3.metric("Drift Issues Found", drift_issues)
    col4.metric("High Severity Issues", high_issues)

    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("#### Pipeline Snapshot")
        snapshot = [
            {"stage": "Ingestion", "artifact": "ingest.json", "status": "Ready" if artifacts.get("ingest") else "Missing"},
            {
                "stage": "AI Documentation",
                "artifact": "generated_docs.json / generated_docs.md",
                "status": "Ready" if artifacts.get("generated_docs") else "Missing",
            },
            {
                "stage": "Drift Detection",
                "artifact": "breaking_changes.json / breaking_changes.md",
                "status": "Ready" if artifacts.get("breaking_changes") else "Missing",
            },
        ]
        st.dataframe(snapshot, hide_index=True, width='stretch')

    with right:
        st.markdown("#### Demo Signal")
        if high_issues:
            st.markdown(
                f"""
                <div class="callout-high">
                  {severity_badge("HIGH")}<br>
                  <strong>{high_issues} high-severity contract issue(s)</strong><br>
                  Drift detector found likely breaking API documentation mismatches.
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.success("No high-severity drift issues detected.")
        st.caption("Generated artifacts are loaded locally from the `output/` folder.")


def render_api_explorer(artifacts: dict[str, Any]) -> None:
    """Render endpoint exploration table and filters."""
    st.subheader("API Explorer")
    endpoints = get_endpoints(artifacts)
    if not endpoints:
        st.info("No endpoints available. Generate `output/ingest.json` first.")
        return

    methods = sorted({clean_text(endpoint.get("method"), "") for endpoint in endpoints if endpoint.get("method")})
    col1, col2 = st.columns([2, 1])
    search = col1.text_input("Search endpoints", placeholder="Search path, controller, method, or query param")
    selected_methods = col2.multiselect("HTTP method", methods, default=methods)

    filtered = filter_endpoints(endpoints, search, selected_methods)
    st.caption(f"Showing {len(filtered)} of {len(endpoints)} endpoints")
    st.dataframe(endpoint_rows(filtered), hide_index=True, width='stretch')

    with st.expander("Endpoint details"):
        for endpoint in filtered:
            st.markdown(f"#### `{endpoint_label(endpoint)}`")
            st.write(f"Controller: `{clean_text(endpoint.get('controller'), '')}`")
            st.write(f"Confidence score: `{endpoint.get('confidence', 'Not available')}`")
            st.write(f"Source file: `{clean_text(endpoint.get('source_file'), '')}`")
            st.caption("Query params")
            render_pills(as_list(endpoint.get("query_params")))


def selected_endpoint(endpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Render endpoint selector and return selected endpoint."""
    if not endpoints:
        return None

    labels = [endpoint_label(endpoint) for endpoint in endpoints]
    selected = st.selectbox("Select endpoint", labels)
    return endpoints[labels.index(selected)]


def render_notes(title: str, values: Any) -> None:
    """Render validation/edge case notes."""
    st.markdown(f"#### {title}")
    notes = as_list(values)
    if not notes:
        st.caption("Not available from extracted source")
        return
    for note in notes:
        st.write(f"- {clean_text(note)}")


def render_generated_docs(artifacts: dict[str, Any]) -> None:
    """Render generated documentation and selected endpoint details."""
    st.subheader("Generated Documentation Viewer")
    generated_docs = artifacts.get("generated_docs", {})
    endpoints = generated_docs.get("endpoints", [])
    generated_markdown = artifacts.get("generated_markdown", "")

    if not endpoints:
        st.info("No generated documentation JSON found. Run the doc generator first.")
        if generated_markdown:
            st.markdown(generated_markdown)
        return

    endpoint = selected_endpoint(endpoints)
    if not endpoint:
        return

    sections = endpoint.get("ai_sections", {})
    st.markdown(f"### `{endpoint_label(endpoint)}`")
    st.markdown(f"Controller: `{clean_text(endpoint.get('controller'), '')}`")
    st.markdown(f"Confidence score: `{endpoint.get('confidence', 'Not available')}`")

    st.markdown("#### Query Params")
    render_pills(as_list(endpoint.get("query_params")))

    left, right = st.columns(2)
    with left:
        st.markdown("#### Request Fields")
        st.dataframe(field_rows(endpoint.get("request_fields", [])), hide_index=True, width='stretch')
    with right:
        st.markdown("#### Response Fields")
        st.dataframe(field_rows(endpoint.get("response_fields", [])), hide_index=True, width='stretch')

    render_notes("Validation Notes", sections.get("validation_notes"))
    render_notes("Edge Cases", sections.get("edge_cases"))

    with st.expander("AI-generated endpoint summary", expanded=True):
        st.markdown(sections.get("endpoint_summary", "Not available from extracted source"))
        st.markdown("##### Sample curl")
        st.code(sections.get("sample_curl", "Not available from extracted source"), language="bash")

    with st.expander("Full generated Markdown document"):
        if generated_markdown:
            st.markdown(generated_markdown)
        else:
            st.caption("`output/generated_docs.md` is missing.")


def render_high_severity(result: dict[str, Any]) -> None:
    """Render one high-severity endpoint callout."""
    high_issues = [issue for issue in result.get("issues", []) if issue.get("severity") == "HIGH"]
    if not high_issues:
        return

    st.markdown(
        f"""
        <div class="callout-high">
          {severity_badge("HIGH")}<br>
          <strong>{clean_text(result.get('method'), '')} {clean_text(result.get('endpoint'), '')}</strong><br>
          {len(high_issues)} high-severity issue(s) detected.
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Review high-severity issues"):
        for issue in high_issues:
            replacement = issue.get("suggested_replacement")
            st.markdown(f"- `{issue.get('type')}` on `{issue.get('field')}`")
            if replacement:
                st.caption(f"Suggested replacement: {replacement}")


def render_drift_dashboard(artifacts: dict[str, Any]) -> None:
    """Render drift findings, PR alerts, and Markdown report."""
    st.subheader("Drift Detection Dashboard")
    breaking_changes = artifacts.get("breaking_changes", {})
    breaking_markdown = artifacts.get("breaking_markdown", "")

    if not breaking_changes:
        st.info("No drift results found. Run the drift detector first.")
        return

    metadata = breaking_changes.get("metadata", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Endpoints Analyzed", metadata.get("endpoints_analyzed", 0))
    col2.metric("Drift Issues", metadata.get("drift_issues_found", 0))
    col3.metric("High Severity", metadata.get("high_severity_issues", 0))

    st.markdown("### High Severity Findings")
    high_results = [result for result in breaking_changes.get("drift_results", []) if result.get("severity") == "HIGH"]
    if not high_results:
        st.success("No high-severity endpoint drift detected.")
    for result in high_results:
        render_high_severity(result)

    issues = all_issues(breaking_changes)
    st.markdown("### Drift Categories")
    tabs = st.tabs(["Removed Fields", "Renamed Fields", "Undocumented Fields"])
    with tabs[0]:
        st.dataframe(issue_rows(issues, {"REMOVED_FIELD"}), hide_index=True, width='stretch')
    with tabs[1]:
        st.dataframe(issue_rows(issues, {"POSSIBLE_RENAMED_FIELD"}), hide_index=True, width='stretch')
    with tabs[2]:
        st.dataframe(
            issue_rows(issues, {"UNDOCUMENTED_RESPONSE_FIELD", "UNDOCUMENTED_QUERY_OR_REQUEST_FIELD"}),
            hide_index=True,
            width='stretch',
        )

    with st.expander("PR-style engineering alerts", expanded=True):
        alerts = as_list(breaking_changes.get("alerts"))
        if alerts:
            for alert in alerts[:12]:
                if alert:
                    st.code(alert, language="text")
            if len(alerts) > 12:
                st.caption(f"Showing 12 of {len(alerts)} alerts.")
        else:
            st.caption("No engineering alerts found.")

    with st.expander("Markdown drift report"):
        if breaking_markdown:
            st.markdown(breaking_markdown)
        else:
            st.caption("`output/breaking_changes.md` is missing.")


def main() -> None:
    """Run the Streamlit app."""
    configure_page()
    repos = load_repos_config()
    page, selected_slug = render_sidebar(repos)

    artifacts = load_artifacts(selected_slug)
    paths = artifacts["paths"]

    render_header()
    render_pipeline_results()
    render_missing_artifacts(artifact_status(paths))

    if page == "Overview Dashboard":
        render_overview(artifacts)
    elif page == "API Explorer":
        render_api_explorer(artifacts)
    elif page == "Generated Documentation Viewer":
        render_generated_docs(artifacts)
    elif page == "Drift Detection Dashboard":
        render_drift_dashboard(artifacts)


if __name__ == "__main__":
    main()
