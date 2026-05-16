---
name: clone_repo
description: Clone a public or credentialed Git repository into the local workspace for analysis.
version: 1.0.0
---

# clone_repo

Clones a Git repository into the API DocAgent workspace using the system `git` binary.
Use this skill when you have direct Git access (SSH or HTTPS with credentials).
For token-only access to GitLab/GitHub without git, use the `gitlab_reader` skill instead.

## Inputs

| Parameter    | Required | Default         | Description                              |
|--------------|----------|-----------------|------------------------------------------|
| `--git-url`  | Yes      | —               | Full Git URL (HTTPS or SSH)              |
| `--target-dir` | No     | `sample_api_go` | Folder name created under project root   |

## Usage

```bash
python skills/clone_repo/scripts/main.py \
  --git-url https://github.com/org/repo.git \
  --target-dir my_service
```

## Behaviour

1. Resolves the project root (two levels above `scripts/`).
2. Checks that the target directory does not already exist — exits early with a message if it does.
3. Runs `git clone <url> <target>` as a subprocess.
4. Prints success or failure with the git exit code.

## Prerequisites

- `git` must be available on `PATH`.
- For private repos, credentials must already be configured (SSH key, credential helper, or token in URL).

## Output

The cloned repository is placed at `<project_root>/<target-dir>/`.
Downstream skills (`doc_ingestor`) can point at this directory for parsing.
