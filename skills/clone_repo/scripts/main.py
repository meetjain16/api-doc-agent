"""Small utility to clone a Git repo into the project for local analysis.

Usage:
  python skills/clone_repo/main.py --git-url <git-url> [--target-dir sample_api_go]

This script uses the system `git` command and will fail if `git` is not installed
or credentials are required and not available.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clone a Git repo into api-doc-agent workspace")
    p.add_argument("--git-url", required=True, help="Git repo URL to clone (read-access)")
    p.add_argument("--target-dir", default="sample_api_go", help="Target folder name under repo root")
    return p.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> None:
    args = parse_args()
    root = repo_root()
    target = root / args.target_dir

    if target.exists():
        print(f"Target already exists: {target}. Remove it first or choose a different --target-dir")
        return

    print(f"Cloning {args.git_url} -> {target}")
    cmd = ["git", "clone", args.git_url, str(target)]
    completed = subprocess.run(cmd)
    if completed.returncode == 0:
        print("Clone complete")
    else:
        print(f"git clone failed with exit {completed.returncode}")


if __name__ == "__main__":
    main()
