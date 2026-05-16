"""Fetch a GitLab repository via API into a local directory.

This is useful when you have a read-only token and do not want to clone the
repository with git. The script downloads repository files into a target folder
that can then be parsed by the rest of the API DocAgent pipeline.

Examples:
  python skills/gitlab_reader/main.py \
    --project mygroup/myservice \
    --token glpat-xxx \
    --target-dir sample_api_go

  python skills/gitlab_reader/main.py \
    --base-url https://gitlab.example.com \
    --project 12345 \
    --branch main \
    --token glpat-xxx
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from urllib.parse import quote_plus

import requests


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a GitLab repo into a local folder")
    parser.add_argument("--base-url", default="https://gitlab.com", help="GitLab base URL")
    parser.add_argument("--project", required=True, help="GitLab project path or numeric ID")
    parser.add_argument("--branch", default="main", help="Branch/ref to fetch")
    parser.add_argument("--token", required=True, help="GitLab read token with repository access")
    parser.add_argument("--target-dir", default="sample_api_go", help="Target folder under repo root")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing target directory")
    return parser.parse_args()


def api_url(base_url: str, project: str, suffix: str) -> str:
    project_ref = quote_plus(project, safe="")
    return f"{base_url.rstrip('/')}/api/v4/projects/{project_ref}{suffix}"


def fetch_tree(session: requests.Session, base_url: str, project: str, branch: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    page = 1
    while True:
        url = api_url(
            base_url,
            project,
            f"/repository/tree?recursive=true&per_page=100&ref={quote_plus(branch)}&page={page}",
        )
        response = session.get(url, timeout=60)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected tree payload: {batch!r}")
        entries.extend(batch)

        next_page = response.headers.get("X-Next-Page", "")
        if not next_page:
            break
        page = int(next_page)

    return entries


def fetch_file(session: requests.Session, base_url: str, project: str, file_path: str, branch: str) -> bytes:
    url = api_url(
        base_url,
        project,
        f"/repository/files/{quote_plus(file_path, safe='')}/raw?ref={quote_plus(branch)}",
    )
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def validate_token_and_project(session: requests.Session, base_url: str, project: str, branch: str) -> None:
    """Validate token permissions and project access before downloading."""
    print(f"[2.5/4] Validating token and project access...")
    
    # Test 1: Check token validity
    try:
        url = f"{base_url.rstrip('/')}/api/v4/user"
        response = session.get(url, timeout=10)
        if response.status_code == 401:
            raise SystemExit(
                "❌ Token authentication failed (401).\n"
                "   • Token may be invalid or expired\n"
                "   • Make sure you're using a PERSONAL ACCESS TOKEN, not a project token\n"
                "   • Token needs 'api' and 'read_repository' scopes\n"
                "   • Check GitLab Settings → Access Tokens"
            )
        response.raise_for_status()
        user = response.json()
        print(f"      ✓ Token valid (user: {user.get('username', 'unknown')})")
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(f"❌ Cannot connect to GitLab at {base_url}\n   {e}")
    except Exception as e:
        raise SystemExit(f"❌ Token validation failed: {e}")
    
    # Test 2: Check project access
    try:
        url = api_url(base_url, project, "")
        response = session.get(url, timeout=10)
        
        if response.status_code == 403:
            raise SystemExit(
                "❌ Access denied to project (403).\n"
                "   • Token has wrong permissions\n"
                "   • Token needs 'api' and 'read_repository' scopes\n"
                "   • You may not have access to this project"
            )
        elif response.status_code == 404:
            raise SystemExit(
                f"❌ Project not found (404): {project}\n"
                "   • Project path may be incorrect\n"
                "   • Use full path like 'group/subgroup/project'\n"
                "   • Or use numeric project ID"
            )
        
        response.raise_for_status()
        proj_info = response.json()
        print(f"      ✓ Project accessible: {proj_info.get('name', project)}")
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(f"❌ Cannot reach GitLab: {e}")
    except Exception as e:
        raise SystemExit(f"❌ Project validation failed: {e}")
    
    # Test 3: Check branch exists
    try:
        url = api_url(base_url, project, f"/repository/branches/{quote_plus(branch)}")
        response = session.get(url, timeout=10)
        
        if response.status_code == 404:
            raise SystemExit(
                f"❌ Branch not found: {branch}\n"
                "   • Check the branch name (case-sensitive)\n"
                "   • Common alternatives: main, master, develop"
            )
        
        response.raise_for_status()
        print(f"      ✓ Branch exists: {branch}")
    except Exception as e:
        raise SystemExit(f"❌ Branch validation failed: {e}")
    
    print(f"[2.5/4] ✓ All validations passed")
def main() -> None:
    args = parse_args()
    root = repo_root()
    target_root = root / args.target_dir

    print(f"[1/4] Checking target directory: {target_root}")
    if target_root.exists():
        if args.overwrite:
            print(f"[1/4] ℹ️  Target exists. Removing old directory...")
            shutil.rmtree(target_root)
            print(f"[1/4] ✓ Removed {target_root}")
        else:
            raise SystemExit(f"❌ Target already exists: {target_root}. Use --overwrite to replace or choose another directory.")
    print(f"[1/4] ✓ Target directory OK")

    print(f"\n[2/4] Authenticating with GitLab...")
    session = requests.Session()
    session.headers.update({"PRIVATE-TOKEN": args.token})
    print(f"[2/4] ✓ Token configured")

    validate_token_and_project(session, args.base_url, args.project, args.branch)

    print(f"\n[3/4] Fetching repository tree...")
    print(f"      Project: {args.project}")
    print(f"      Branch: {args.branch}")
    print(f"      Base URL: {args.base_url}")
    try:
        tree = fetch_tree(session, args.base_url, args.project, args.branch)
        blobs = [entry for entry in tree if entry.get("type") == "blob"]
        print(f"[3/4] ✓ Found {len(blobs)} files to download")
    except requests.exceptions.HTTPError as e:
        error_msg = f"❌ GitLab API error: {e.response.status_code}\n"
        if e.response.text:
            error_msg += f"    Response: {e.response.text[:200]}\n"
        error_msg += "    Check:\n"
        error_msg += "    • Token is valid and not expired\n"
        error_msg += "    • Project path is correct (use full path: group/project)\n"
        error_msg += "    • Branch name exists and is spelled correctly\n"
        raise SystemExit(error_msg)
    except Exception as e:
        raise SystemExit(f"❌ Error fetching tree: {e}")

    print(f"\n[4/4] Downloading files...")
    target_root.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failed = 0
    
    for idx, entry in enumerate(blobs, 1):
        file_path = str(entry.get("path", ""))
        if not file_path:
            continue

        try:
            content = fetch_file(session, args.base_url, args.project, file_path, args.branch)
            output_path = target_root / file_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            downloaded += 1
            if idx % 50 == 0:
                print(f"[4/4] Downloaded {downloaded}/{len(blobs)} files...")
        except Exception as e:
            print(f"[4/4] ⚠️  Failed to download {file_path}: {e}")
            failed += 1

    print(f"\n[4/4] ✓ Download complete")
    print(f"✓ Successfully downloaded {downloaded} files into {target_root}")
    if failed > 0:
        print(f"⚠️  {failed} files failed to download (non-critical)")


if __name__ == "__main__":
    main()
