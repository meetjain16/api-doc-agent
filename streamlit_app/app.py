"""Streamlit dashboard for the API DocAgent hackathon demo."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import subprocess
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
        /* ── Base ─────────────────────────────────────────────── */
        .stApp { background: #0d1117; color: #e6edf3; }
        .main .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }

        /* ── Global text ──────────────────────────────────────── */
        h1, h2, h3, h4, h5, h6 { color: #f0f6fc !important; }
        p, li, span, div { color: #e6edf3; }
        .stMarkdown p, .stMarkdown li { color: #c9d1d9 !important; }
        label, .stCaption, [data-testid="stCaption"] { color: #8b949e !important; }
        code { color: #79c0ff !important; background: #161b22 !important; padding: .1rem .3rem; border-radius: 4px; }

        /* ── Sidebar ──────────────────────────────────────────── */
        [data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }
        [data-testid="stSidebar"] * { color: #c9d1d9 !important; }
        [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 { color: #f0f6fc !important; }
        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stRadio label { color: #c9d1d9 !important; }

        /* ── Buttons ──────────────────────────────────────────── */
        button[kind="primary"], .stButton > button[kind="primary"] {
            background: linear-gradient(135deg,#2563eb,#1d4ed8);
            color: #fff !important;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            padding: .45rem 1.1rem;
            box-shadow: 0 2px 8px rgba(37,99,235,.35);
            transition: opacity .15s;
        }
        button[kind="primary"]:hover { opacity: .88; }
        .stButton > button {
            background: #21262d;
            color: #c9d1d9 !important;
            border: 1px solid #30363d;
            border-radius: 6px;
            font-weight: 500;
            transition: background .15s, border-color .15s;
        }
        .stButton > button:hover {
            background: #30363d;
            border-color: #58a6ff;
            color: #58a6ff !important;
        }

        /* ── Inputs / Selects ─────────────────────────────────── */
        .stTextInput input { background: #161b22 !important; color: #c9d1d9 !important; border-color: #30363d !important; border-radius: 6px !important; }

        /* Selectbox container */
        div[data-baseweb="select"] > div {
            background: #161b22 !important;
            border-color: #30363d !important;
            border-radius: 6px !important;
        }
        /* Selected value text */
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div,
        div[data-baseweb="select"] p {
            color: #c9d1d9 !important;
            background: transparent !important;
        }
        /* Dropdown popover / list container */
        div[data-baseweb="popover"],
        ul[data-baseweb="menu"] {
            background: #1c2128 !important;
            border: 1px solid #30363d !important;
            border-radius: 8px !important;
        }
        /* Each option */
        li[role="option"],
        div[role="option"] {
            background: #1c2128 !important;
            color: #c9d1d9 !important;
        }
        li[role="option"]:hover,
        div[role="option"]:hover,
        li[role="option"][aria-selected="true"],
        div[role="option"][aria-selected="true"] {
            background: #2d333b !important;
            color: #f0f6fc !important;
        }
        /* Option text spans */
        li[role="option"] span,
        li[role="option"] div,
        div[role="option"] span,
        div[role="option"] div {
            color: #c9d1d9 !important;
            background: transparent !important;
        }
        /* Multiselect tags */
        span[data-baseweb="tag"] {
            background: #21262d !important;
            color: #79c0ff !important;
        }
        /* Radio buttons */
        div[data-testid="stRadio"] label { color: #c9d1d9 !important; }
        div[data-testid="stRadio"] label:hover { color: #f0f6fc !important; }
        /* Checkbox */
        div[data-testid="stCheckbox"] label { color: #c9d1d9 !important; }

        /* ── Metrics ──────────────────────────────────────────── */
        div[data-testid="stMetric"] {
            background: #161b22; border: 1px solid #30363d;
            border-radius: 8px; padding: 1rem;
            box-shadow: 0 4px 12px rgba(0,0,0,.4);
        }
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] { color: #8b949e !important; font-size: .85rem; }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f0f6fc !important; font-size: 1.6rem; font-weight: 700; }

        /* ── Expanders ────────────────────────────────────────── */
        div[data-testid="stExpander"] {
            background: #161b22 !important;
            border: 1px solid #30363d !important;
            border-radius: 8px;
        }
        div[data-testid="stExpander"] summary { color: #c9d1d9 !important; font-weight: 600; }
        div[data-testid="stExpander"] summary:hover { color: #58a6ff !important; }
        div[data-testid="stExpander"] > div { color: #c9d1d9 !important; }
        div[data-testid="stExpander"] p,
        div[data-testid="stExpander"] li { color: #c9d1d9 !important; }

        /* ── Tabs ─────────────────────────────────────────────── */
        div[data-testid="stTabs"] button { color: #8b949e !important; font-weight: 500; }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: #58a6ff !important;
            border-bottom: 2px solid #58a6ff !important;
            font-weight: 700;
        }

        /* ── DataFrames ───────────────────────────────────────── */
        div[data-testid="stDataFrame"] { border-radius: 8px; border: 1px solid #30363d; overflow: hidden; }
        div[data-testid="stDataFrame"] th { background: #1c2128 !important; color: #8b949e !important; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
        div[data-testid="stDataFrame"] td { color: #c9d1d9 !important; background: #0d1117 !important; }

        /* ── Custom components ────────────────────────────────── */
        .hero {
            border: 1px solid #30363d;
            border-left: 4px solid #58a6ff;
            border-radius: 8px;
            padding: 1rem 1.4rem;
            background: #161b22;
            margin-bottom: 1.2rem;
        }
        .hero h1 { font-size: 1.7rem; margin: 0 0 .25rem 0; color: #f0f6fc !important; }
        .hero p { margin: 0; color: #8b949e !important; }

        .info-card {
            border: 1px solid #30363d;
            border-radius: 8px;
            background: #161b22;
            padding: .9rem 1rem;
            margin-bottom: .75rem;
        }
        .info-card p, .info-card span, .info-card div { color: #c9d1d9 !important; }
        .info-card b, .info-card strong { color: #f0f6fc !important; }

        .ep-header {
            border: 1px solid #30363d;
            border-radius: 10px;
            background: #161b22;
            padding: 1rem 1.2rem;
            margin-bottom: 1rem;
        }
        .ep-header code { font-size: 1.05rem !important; color: #f0f6fc !important; background: transparent !important; }

        .method-badge {
            display: inline-block;
            font-size: .78rem; font-weight: 700;
            padding: .22rem .7rem; border-radius: 5px;
            margin-right: .5rem; letter-spacing: .04em;
        }
        .method-GET    { background:#0d4429; color:#3fb950; border:1px solid #3fb950; }
        .method-POST   { background:#0c2d6b; color:#58a6ff; border:1px solid #58a6ff; }
        .method-PUT    { background:#3d2900; color:#e3b341; border:1px solid #e3b341; }
        .method-DELETE { background:#67060c; color:#ff7b72; border:1px solid #ff7b72; }
        .method-PATCH  { background:#2d1f6e; color:#bc8cff; border:1px solid #bc8cff; }

        .ai-status-ai       { display:inline-block; background:#0d4429; color:#3fb950; border:1px solid #3fb950; border-radius:4px; font-size:.72rem; font-weight:700; padding:.15rem .5rem; }
        .ai-status-fallback { display:inline-block; background:#3d2900; color:#e3b341; border:1px solid #e3b341; border-radius:4px; font-size:.72rem; font-weight:700; padding:.15rem .5rem; }

        .section-block {
            border: 1px solid #30363d;
            border-left: 3px solid #58a6ff;
            border-radius: 0 8px 8px 0;
            background: #161b22;
            padding: .75rem 1rem;
            margin-bottom: .6rem;
        }
        .section-block p, .section-block li { color: #c9d1d9 !important; }
        .section-block .section-title { color: #8b949e !important; font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; margin-bottom: .3rem; }

        .pill {
            display: inline-block;
            border: 1px solid #30363d;
            border-radius: 999px;
            padding: .15rem .55rem;
            margin: .1rem .15rem .1rem 0;
            background: #21262d;
            color: #79c0ff !important;
            font-size: .8rem; font-family: monospace;
        }

        .badge { display:inline-block; border-radius:999px; padding:.18rem .55rem; font-size:.75rem; font-weight:700; border:1px solid transparent; line-height:1.35; }
        .badge-high   { background:#67060c; color:#ff7b72 !important; border-color:#ff7b72; }
        .badge-medium { background:#3d2900; color:#e3b341 !important; border-color:#e3b341; }
        .badge-low    { background:#0c2d6b; color:#58a6ff !important; border-color:#58a6ff; }
        .badge-none   { background:#0d4429; color:#3fb950 !important; border-color:#3fb950; }

        .callout-high   { border:1px solid #ff7b72; border-left:5px solid #f85149; border-radius:8px; background:#1c1014; color:#ff7b72 !important; padding:.85rem 1rem; margin-bottom:.75rem; }
        .callout-high * { color:#ff7b72 !important; }
        .callout-medium   { border:1px solid #e3b341; border-left:5px solid #d29922; border-radius:8px; background:#1c180e; color:#e3b341 !important; padding:.85rem 1rem; margin-bottom:.75rem; }
        .callout-medium * { color:#e3b341 !important; }
        .callout-low   { border:1px solid #58a6ff; border-left:5px solid #388bfd; border-radius:8px; background:#0d1e36; color:#79c0ff !important; padding:.85rem 1rem; margin-bottom:.75rem; }
        .callout-low * { color:#79c0ff !important; }

        .muted { color: #8b949e !important; }

        /* ── Download buttons ─────────────────────────────────── */
        .stDownloadButton > button {
            background: #21262d !important;
            color: #79c0ff !important;
            border: 1px solid #30363d !important;
            border-radius: 6px !important;
            font-size: .82rem !important;
            font-weight: 500 !important;
            padding: .35rem .85rem !important;
            transition: background .15s, border-color .15s !important;
        }
        .stDownloadButton > button:hover {
            background: #2d333b !important;
            border-color: #79c0ff !important;
            color: #a5d6ff !important;
        }

        /* ── Hero gradient ────────────────────────────────────── */
        .hero-v2 {
            background: linear-gradient(135deg, #0d1117 0%, #0c1a2e 60%, #0d1117 100%);
            border: 1px solid #30363d;
            border-left: 4px solid #58a6ff;
            border-radius: 10px;
            padding: 1.4rem 1.6rem;
            margin-bottom: 1.4rem;
            position: relative;
            overflow: hidden;
        }
        .hero-v2::before {
            content: '';
            position: absolute;
            top: -40px; right: -40px;
            width: 200px; height: 200px;
            background: radial-gradient(circle, rgba(88,166,255,.12) 0%, transparent 70%);
            pointer-events: none;
        }
        .hero-v2 h1 { font-size: 1.65rem; margin: 0 0 .3rem 0; color: #f0f6fc !important; letter-spacing: -.02em; }
        .hero-v2 .hero-sub { color: #8b949e !important; font-size: .9rem; margin: 0; }
        .hero-v2 .hero-chips { margin-top: .7rem; display: flex; gap: .5rem; flex-wrap: wrap; }
        .hero-chip { background: #21262d; border: 1px solid #30363d; border-radius: 999px; padding: .18rem .65rem; font-size: .75rem; color: #79c0ff !important; font-family: monospace; }

        /* ── Stat card ────────────────────────────────────────── */
        .stat-card {
            background: linear-gradient(145deg, #161b22, #0d1117);
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 1.1rem 1.2rem;
            text-align: center;
        }
        .stat-card .stat-val { font-size: 2rem; font-weight: 800; color: #f0f6fc !important; line-height: 1.1; }
        .stat-card .stat-lbl { font-size: .78rem; color: #8b949e !important; text-transform: uppercase; letter-spacing: .06em; margin-top: .25rem; }
        .stat-card .stat-sub { font-size: .75rem; color: #58a6ff !important; margin-top: .2rem; }

        /* ── Section divider label ────────────────────────────── */
        .section-label {
            font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em;
            color: #8b949e !important; margin: 1.2rem 0 .5rem 0; border-bottom: 1px solid #21262d; padding-bottom: .3rem;
        }

        /* ── Endpoint row card ────────────────────────────────── */
        .ep-row {
            display: flex; align-items: center; gap: .75rem;
            background: #161b22; border: 1px solid #30363d; border-radius: 8px;
            padding: .65rem 1rem; margin-bottom: .4rem; cursor: pointer;
        }
        .ep-row:hover { border-color: #58a6ff; background: #1c2128; }
        .ep-row .ep-path { font-family: monospace; color: #c9d1d9 !important; font-size: .9rem; }
        .ep-row .ep-controller { color: #8b949e !important; font-size: .78rem; margin-left: auto; }

        /* ── Confidence indicator ─────────────────────────────── */
        .conf-high   { color: #3fb950 !important; font-weight: 700; }
        .conf-medium { color: #e3b341 !important; font-weight: 700; }
        .conf-low    { color: #ff7b72 !important; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render product header."""
    st.markdown(
        f"""
        <div class="hero-v2">
          <h1>API DocAgent</h1>
          <p class="hero-sub">AI-Powered API Intelligence Platform &nbsp;·&nbsp; Hackathon Demo</p>
          <div class="hero-chips">
            <span class="hero-chip">Route Discovery</span>
            <span class="hero-chip">Schema Extraction</span>
            <span class="hero-chip">AI Documentation</span>
            <span class="hero-chip">Drift Detection</span>
            <span class="hero-chip">Go + FastAPI</span>
          </div>
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


def _endpoints_to_csv(endpoints: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["method", "path", "controller", "confidence", "source_file", "query_params"])
    writer.writeheader()
    for ep in endpoints:
        writer.writerow({
            "method": clean_text(ep.get("method"), ""),
            "path": clean_text(ep.get("path"), ""),
            "controller": clean_text(ep.get("controller"), ""),
            "confidence": ep.get("confidence", ""),
            "source_file": clean_text(ep.get("source_file"), ""),
            "query_params": ", ".join(str(p) for p in as_list(ep.get("query_params"))),
        })
    return buf.getvalue().encode()


def _endpoint_to_md(endpoint: dict[str, Any]) -> bytes:
    sections = endpoint.get("ai_sections", {})
    method = clean_text(endpoint.get("method"), "GET").upper()
    path = clean_text(endpoint.get("path"), "")
    controller = clean_text(endpoint.get("controller"), "")
    query_params = ", ".join(str(p) for p in as_list(endpoint.get("query_params"))) or "None"
    curl = clean_text(sections.get("sample_curl"), "")

    lines = [
        f"## {method} {path}",
        f"",
        f"**Controller:** `{controller}`  ",
        f"**Query Params:** `{query_params}`",
        f"",
        f"### Summary",
        clean_text(sections.get("endpoint_summary"), "_Not available_"),
        f"",
        f"### Business Context",
        clean_text(sections.get("business_summary"), "_Not available_"),
        f"",
        f"### Request",
        clean_text(sections.get("request_explanation"), "_Not available_"),
        f"",
        f"### Response",
        clean_text(sections.get("response_explanation"), "_Not available_"),
    ]
    if curl:
        lines += ["", "### Sample curl", "```bash", curl, "```"]
    return "\n".join(lines).encode()


def _dl_row(*items: tuple) -> None:
    """Render a row of download buttons. Each item: (label, data, filename, mime)."""
    cols = st.columns(len(items))
    for col, (label, data, filename, mime) in zip(cols, items):
        col.download_button(label, data=data, file_name=filename, mime=mime, use_container_width=True)


def render_overview(artifacts: dict[str, Any]) -> None:
    """Render overview metrics."""
    ingest_meta = artifacts.get("ingest", {}).get("metadata", {})
    drift_meta = artifacts.get("breaking_changes", {}).get("metadata", {})
    generated_meta = artifacts.get("generated_docs", {}).get("metadata", {})

    total_apis = ingest_meta.get("total_endpoints") or generated_meta.get("generated_endpoints") or 0
    total_structs = ingest_meta.get("total_structs") or generated_meta.get("input_total_structs") or 0
    drift_issues = drift_meta.get("drift_issues_found", 0)
    high_issues = drift_meta.get("high_severity_issues", 0)
    ai_generated = generated_meta.get("generated_endpoints", 0)

    st.subheader("Overview Dashboard")
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, lbl, sub, color in [
        (c1, total_apis, "APIs Parsed", "endpoints", "#58a6ff"),
        (c2, total_structs, "Structs", "extracted", "#bc8cff"),
        (c3, ai_generated, "AI Docs", "generated", "#3fb950"),
        (c4, drift_issues, "Drift Issues", "detected", "#e3b341"),
        (c5, high_issues, "High Severity", "critical", "#ff7b72"),
    ]:
        col.markdown(
            f'<div class="stat-card"><div class="stat-val" style="color:{color}!important">{val}</div>'
            f'<div class="stat-lbl">{lbl}</div><div class="stat-sub">{sub}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-label">Pipeline Artifacts</div>', unsafe_allow_html=True)
    left, right = st.columns([1.3, 1])
    with left:
        snapshot = [
            {"Stage": "Ingestion", "Artifact": "ingest.json", "Status": "✓ Ready" if artifacts.get("ingest") else "○ Missing"},
            {"Stage": "AI Documentation", "Artifact": "generated_docs.json / .md", "Status": "✓ Ready" if artifacts.get("generated_docs") else "○ Missing"},
            {"Stage": "Drift Detection", "Artifact": "breaking_changes.json / .md", "Status": "✓ Ready" if artifacts.get("breaking_changes") else "○ Missing"},
        ]
        st.dataframe(snapshot, hide_index=True, width='stretch')

    with right:
        if high_issues:
            st.markdown(
                f"""
                <div class="callout-high">
                  {severity_badge("HIGH")}&nbsp;&nbsp;<strong>{high_issues} high-severity contract issue(s)</strong><br>
                  <span style="font-size:.85rem">Drift detector found breaking API documentation mismatches.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif drift_issues:
            st.markdown(
                f'<div class="callout-medium">{severity_badge("MEDIUM")}&nbsp;&nbsp;<strong>{drift_issues} drift issue(s)</strong><br>'
                f'<span style="font-size:.85rem">No high-severity issues, but drift was detected.</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="callout-low">✓ &nbsp;<strong>No drift issues detected.</strong><br><span style="font-size:.85rem">All endpoints appear consistent.</span></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-label">Download Artifacts</div>', unsafe_allow_html=True)
    dl_cols = st.columns(4)
    paths = artifacts["paths"]

    def _file_bytes(p: Path) -> bytes:
        return p.read_bytes() if p.exists() else b""

    dl_cols[0].download_button("⬇ ingest.json", data=_file_bytes(paths["ingest"]), file_name="ingest.json", mime="application/json", use_container_width=True, disabled=not paths["ingest"].exists())
    dl_cols[1].download_button("⬇ generated_docs.json", data=_file_bytes(paths["generated_docs_json"]), file_name="generated_docs.json", mime="application/json", use_container_width=True, disabled=not paths["generated_docs_json"].exists())
    dl_cols[2].download_button("⬇ generated_docs.md", data=_file_bytes(paths["generated_docs_md"]), file_name="generated_docs.md", mime="text/markdown", use_container_width=True, disabled=not paths["generated_docs_md"].exists())
    dl_cols[3].download_button("⬇ breaking_changes.json", data=_file_bytes(paths["breaking_changes_json"]), file_name="breaking_changes.json", mime="application/json", use_container_width=True, disabled=not paths["breaking_changes_json"].exists())


def render_api_explorer(artifacts: dict[str, Any]) -> None:
    """Render endpoint exploration table and filters."""
    st.subheader("API Explorer")
    endpoints = get_endpoints(artifacts)
    if not endpoints:
        st.info("No endpoints available. Generate `output/ingest.json` first.")
        return

    methods = sorted({clean_text(endpoint.get("method"), "") for endpoint in endpoints if endpoint.get("method")})
    col1, col2, col3 = st.columns([2, 1, 0.6])
    search = col1.text_input("Search endpoints", placeholder="Search path, controller, method, or query param")
    selected_methods = col2.multiselect("HTTP method", methods, default=methods)
    filtered = filter_endpoints(endpoints, search, selected_methods)
    col3.markdown("<div style='margin-top:1.8rem'></div>", unsafe_allow_html=True)
    col3.download_button(
        "⬇ CSV",
        data=_endpoints_to_csv(filtered),
        file_name="endpoints.csv",
        mime="text/csv",
        use_container_width=True,
    )

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


_METHOD_COLORS = {
    "GET": "#3fb950", "POST": "#58a6ff", "PUT": "#e3b341",
    "DELETE": "#ff7b72", "PATCH": "#bc8cff",
}
_NA = "Not available from extracted source"


def _section_text(value: Any) -> str:
    text = clean_text(value, "")
    return "" if text == _NA or not text else text


def _render_section_block(title: str, text: str) -> None:
    if not text:
        return
    st.markdown(
        f'<div class="section-block"><div class="section-title">{title}</div><p>{text}</p></div>',
        unsafe_allow_html=True,
    )


def render_generated_docs(artifacts: dict[str, Any]) -> None:
    """Render generated documentation viewer with full endpoint detail."""
    st.subheader("Generated Documentation Viewer")
    generated_docs = artifacts.get("generated_docs", {})
    endpoints = generated_docs.get("endpoints", [])
    generated_markdown = artifacts.get("generated_markdown", "")

    if not endpoints:
        st.info("No generated documentation found. Select a repo and click Run Pipeline.")
        return

    # Download full docs
    paths = artifacts["paths"]
    dl1, dl2, dl3 = st.columns([1, 1, 4])
    if paths["generated_docs_md"].exists():
        dl1.download_button("⬇ Full Docs (.md)", data=paths["generated_docs_md"].read_bytes(), file_name="generated_docs.md", mime="text/markdown")
    if paths["generated_docs_json"].exists():
        dl2.download_button("⬇ Full Docs (.json)", data=paths["generated_docs_json"].read_bytes(), file_name="generated_docs.json", mime="application/json")

    st.divider()

    # Endpoint selector
    endpoint = selected_endpoint(endpoints)
    if not endpoint:
        return

    sections = endpoint.get("ai_sections", {})
    method = clean_text(endpoint.get("method"), "GET").upper()
    path = clean_text(endpoint.get("path"), "")
    controller = clean_text(endpoint.get("controller"), "")
    source_file = clean_text(endpoint.get("source_file"), "")
    confidence = endpoint.get("confidence", "")
    is_ai = sections.get("generation_status") == "ai"
    tags = as_list(endpoint.get("tags"))
    query_params = as_list(endpoint.get("query_params"))
    path_params = as_list(endpoint.get("path_params", []))
    request_structs = as_list(endpoint.get("request_structs"))
    response_structs = as_list(endpoint.get("response_structs"))

    status_badge = '<span class="ai-status-ai">AI</span>' if is_ai else '<span class="ai-status-fallback">Fallback</span>'
    tag_html = "".join(f'<span class="pill">{t}</span>' for t in tags) if tags else ""

    st.markdown(
        f"""
        <div class="ep-header">
          <div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-bottom:.6rem">
            <span class="method-badge method-{method}">{method}</span>
            <code>{path}</code>
            {status_badge}
          </div>
          <div style="display:flex;gap:2rem;flex-wrap:wrap;font-size:.84rem;color:#8b949e">
            <span>Controller: <code>{controller}</code></span>
            <span>File: <code>{source_file}</code></span>
            <span>Confidence: <code>{confidence}</code></span>
          </div>
          {f'<div style="margin-top:.5rem">{tag_html}</div>' if tag_html else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tabs: Overview · Parameters · Schema · Developer Tools
    tab_overview, tab_params, tab_schema, tab_dev = st.tabs(
        ["Overview", "Parameters & Fields", "Request / Response", "Developer Tools"]
    )

    with tab_overview:
        summary = _section_text(sections.get("endpoint_summary"))
        business = _section_text(sections.get("business_summary"))
        req_exp = _section_text(sections.get("request_explanation"))
        resp_exp = _section_text(sections.get("response_explanation"))

        if not any([summary, business, req_exp, resp_exp]):
            st.info(
                "AI documentation was not generated. "
                "Add a valid ANTHROPIC_API_KEY (starting with sk-ant-) to .env and re-run the pipeline."
            )
        else:
            _render_section_block("Endpoint Summary", summary)
            _render_section_block("Business Context", business)
            _render_section_block("Request", req_exp)
            _render_section_block("Response", resp_exp)

        val_notes = [v for v in as_list(sections.get("validation_notes")) if v and v != _NA]
        edge_cases = [e for e in as_list(sections.get("edge_cases")) if e and e != _NA]
        if val_notes or edge_cases:
            c1, c2 = st.columns(2)
            with c1:
                if val_notes:
                    st.markdown("**Validation Notes**")
                    for note in val_notes:
                        st.markdown(f"- {note}")
            with c2:
                if edge_cases:
                    st.markdown("**Edge Cases**")
                    for case in edge_cases:
                        st.markdown(f"- {case}")

    with tab_params:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Query Parameters**")
            render_pills(query_params)
            if path_params:
                st.markdown("**Path Parameters**")
                render_pills(path_params)
        with c2:
            st.markdown("**Request Structs**")
            render_pills(request_structs)
            if response_structs:
                st.markdown("**Response Structs**")
                render_pills(response_structs)

    with tab_schema:
        rf = field_rows(endpoint.get("request_fields", []))
        rsf = field_rows(endpoint.get("response_fields", []))

        st.markdown("**Request Fields**")
        if rf:
            st.dataframe(rf, hide_index=True, width='stretch')
        else:
            st.caption("No request struct fields resolved. Struct may be defined in an external dependency.")

        st.divider()

        st.markdown("**Response Fields**")
        if rsf:
            st.dataframe(rsf, hide_index=True, width='stretch')
        else:
            st.caption("No response struct fields resolved. Response model may be dynamic or not yet inferred.")

        schema_text = _section_text(sections.get("openapi_schema_summary"))
        if schema_text:
            st.divider()
            st.markdown("**OpenAPI-style Schema Summary**")
            st.code(schema_text, language="yaml")

    with tab_dev:
        curl = _section_text(sections.get("sample_curl"))
        dl_c1, dl_c2 = st.columns([1, 1])
        ep_slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "endpoint"
        dl_c1.download_button(
            "⬇ This endpoint (.md)",
            data=_endpoint_to_md(endpoint),
            file_name=f"{ep_slug}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        dl_c2.download_button(
            "⬇ This endpoint (.json)",
            data=json.dumps(endpoint, indent=2, ensure_ascii=False).encode(),
            file_name=f"{ep_slug}.json",
            mime="application/json",
            use_container_width=True,
        )

        st.divider()
        if curl:
            st.markdown("**Sample curl**")
            st.code(curl, language="bash")
        else:
            params = {p: "demo" for p in query_params}
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            fallback_curl = f"curl -X {method} 'http://localhost:8080{path}{'?' + qs if qs else ''}'"
            st.markdown("**Sample curl** *(auto-generated)*")
            st.code(fallback_curl, language="bash")

        st.divider()
        with st.expander("Full generated Markdown document", expanded=False):
            if generated_markdown:
                st.markdown(generated_markdown)
            else:
                st.caption("`output/generated_docs.md` not found.")


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
    paths = artifacts["paths"]

    if not breaking_changes:
        st.info("No drift results found. Run the drift detector first.")
        return

    metadata = breaking_changes.get("metadata", {})
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Endpoints Analyzed", metadata.get("endpoints_analyzed", 0))
    col2.metric("Drift Issues", metadata.get("drift_issues_found", 0))
    col3.metric("High Severity", metadata.get("high_severity_issues", 0))
    if paths["breaking_changes_md"].exists():
        col4.download_button("⬇ Report (.md)", data=paths["breaking_changes_md"].read_bytes(), file_name="breaking_changes.md", mime="text/markdown", use_container_width=True)
    if paths["breaking_changes_json"].exists():
        col5.download_button("⬇ Report (.json)", data=paths["breaking_changes_json"].read_bytes(), file_name="breaking_changes.json", mime="application/json", use_container_width=True)

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
