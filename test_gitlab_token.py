#!/usr/bin/env python3
"""Quick diagnostic test for GitLab token and project access.

Usage:
  python test_gitlab_token.py \
    --base-url https://scm.intermesh.net \
    --project indiamart/search/product-search-screen \
    --token YOUR_TOKEN_HERE
"""

import argparse
import sys
from urllib.parse import quote_plus
import requests


def test_connection(base_url: str) -> bool:
    """Test basic connectivity to GitLab server."""
    print("🔌 [1/4] Testing connection to GitLab...")
    try:
        response = requests.get(f"{base_url}/api/v4/version", timeout=5)
        if response.status_code == 401:
            print("    ✓ GitLab server reachable")
            print("      ℹ️  /api/v4/version is protected on this instance, so 401 is expected")
            return True

        response.raise_for_status()
        version = response.json().get("version", "unknown")
        print(f"    ✓ Connected to GitLab {version}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"    ❌ Cannot connect to {base_url}")
        print(f"       Check the URL and network connectivity")
        return False
    except Exception as e:
        print(f"    ❌ Connection test failed: {e}")
        return False


def test_token(base_url: str, token: str) -> bool:
    """Test if token is valid."""
    print("\n🔑 [2/4] Testing token authentication...")
    session = requests.Session()
    session.headers.update({"PRIVATE-TOKEN": token})
    
    try:
        response = session.get(f"{base_url}/api/v4/user", timeout=5)
        
        if response.status_code == 401:
            print(f"    ❌ Token rejected (401)")
            print(f"       • Token may be invalid or expired")
            print(f"       • Token should be a PERSONAL ACCESS TOKEN")
            print(f"       • Check GitLab Settings → Access Tokens")
            return False
        
        response.raise_for_status()
        user = response.json()
        username = user.get("username", "unknown")
        print(f"    ✓ Token valid (user: {username})")
        return True
    except Exception as e:
        print(f"    ❌ Token test failed: {e}")
        return False


def test_project_access(base_url: str, token: str, project: str) -> bool:
    """Test if token can access the project."""
    print(f"\n📁 [3/4] Testing project access: {project}")
    session = requests.Session()
    session.headers.update({"PRIVATE-TOKEN": token})
    
    project_ref = quote_plus(project, safe="")
    url = f"{base_url}/api/v4/projects/{project_ref}"
    
    try:
        response = session.get(url, timeout=5)
        
        if response.status_code == 403:
            print(f"    ❌ Access denied (403)")
            print(f"       • Token lacks required permissions")
            print(f"       • Token needs 'api' and 'read_repository' scopes")
            print(f"       • You may not have access to this project")
            return False
        
        if response.status_code == 404:
            print(f"    ❌ Project not found (404)")
            print(f"       • Project path may be incorrect")
            print(f"       • Use full path: 'group/subgroup/project'")
            print(f"       • Or use numeric project ID")
            return False
        
        response.raise_for_status()
        proj = response.json()
        print(f"    ✓ Project accessible: {proj.get('name', project)}")
        return True
    except Exception as e:
        print(f"    ❌ Project test failed: {e}")
        return False


def test_repository_access(base_url: str, token: str, project: str, branch: str) -> bool:
    """Test if token can read repository."""
    print(f"\n📚 [4/4] Testing repository access ({branch})...")
    session = requests.Session()
    session.headers.update({"PRIVATE-TOKEN": token})
    
    project_ref = quote_plus(project, safe="")
    url = f"{base_url}/api/v4/projects/{project_ref}/repository/tree?recursive=true&per_page=1&ref={quote_plus(branch)}"
    
    try:
        response = session.get(url, timeout=5)
        
        if response.status_code == 404:
            print(f"    ❌ Branch not found (404): {branch}")
            print(f"       • Check the branch name (case-sensitive)")
            print(f"       • Try 'main', 'master', or 'develop'")
            return False
        
        response.raise_for_status()
        data = response.json()
        print(f"    ✓ Repository readable (can fetch files)")
        return True
    except Exception as e:
        print(f"    ❌ Repository test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test GitLab token and project access")
    parser.add_argument("--base-url", default="https://scm.intermesh.net", help="GitLab base URL")
    parser.add_argument("--project", required=True, help="GitLab project path or ID")
    parser.add_argument("--token", required=True, help="GitLab read token")
    parser.add_argument("--branch", default="main", help="Branch to test")
    args = parser.parse_args()
    
    print("=" * 60)
    print("GitLab Token & Project Access Diagnostics")
    print("=" * 60)
    
    results = {
        "Connection": test_connection(args.base_url),
        "Token": test_token(args.base_url, args.token),
        "Project": test_project_access(args.base_url, args.token, args.project),
        "Repository": test_repository_access(args.base_url, args.token, args.project, args.branch),
    }
    
    print("\n" + "=" * 60)
    print("Summary:")
    for test, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test}")
    print("=" * 60)
    
    if all(results.values()):
        print("\n✓ All checks passed! Your token should work.")
        return 0
    else:
        print("\n❌ Some checks failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
