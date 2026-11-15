#!/usr/bin/env python3
"""
Unjobless - Granular Auto-Commit & Auto-Push Daemon
Monitors repository changes, decomposes them into atomic, semantic git commits,
and pushes them to GitHub.

Author/Committer: galiihajiip <gajipgaming@gmail.com>
Repository: https://github.com/galiihajiip/Unjobless.git
"""

import os
import re
import sys
import time
import subprocess
import argparse
from pathlib import Path

# Git identity configuration
GIT_AUTHOR_NAME = "galiihajiip"
GIT_AUTHOR_EMAIL = "gajipgaming@gmail.com"

# Ignored patterns that should never be staged
IGNORED_PATTERNS = [
    r"\.DS_Store$",
    r"\.swp$",
    r"~$",
    r"\.tmp$",
    r"^cv\.",
    r"\.docx$",
    r"\.doc$",
    r"^private/",
    r"^data/",
    r"^uploads/",
    r"\.env$",
    r"\.env\.local$",
]

def run_cmd(cmd, cwd=None, env=None, check=True):
    """Run a shell command and return stdout."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    res = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=isinstance(cmd, str),
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed [{res.returncode}]: {cmd}\nSTDERR: {res.stderr}")
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def is_ignored(path_str):
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, path_str, re.IGNORECASE):
            return True
    return False

def get_current_branch():
    out, _, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return out or "main"

def ensure_git_config():
    """Ensure local repository has the right identity and remote."""
    run_cmd(["git", "config", "user.name", GIT_AUTHOR_NAME])
    run_cmd(["git", "config", "user.email", GIT_AUTHOR_EMAIL])

def get_git_status():
    """
    Get porcelain v1 status with untracked files listed individually.
    Returns list of tuples: (status_code, file_path, orig_path_if_rename)
    """
    out, _, code = run_cmd(["git", "status", "--porcelain=v1", "-uall"], check=False)
    if code != 0 or not out:
        return []

    items = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        status_code = line[0:2]
        file_part = line[3:].strip()

        # Handle renames: R  old -> new
        if " -> " in file_part:
            old_p, new_p = file_part.split(" -> ", 1)
            old_p = old_p.strip('"')
            new_p = new_p.strip('"')
            if not is_ignored(new_p):
                items.append((status_code.strip(), new_p, old_p))
        else:
            p = file_part.strip('"')
            if not is_ignored(p):
                items.append((status_code.strip(), p, None))
    return items

def infer_scope(file_path):
    """Infer a concise, meaningful scope from the file path."""
    p = Path(file_path)
    parts = p.parts

    if len(parts) == 1:
        # Root level files
        name = parts[0].lower()
        if name in ("package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock"):
            return "deps"
        if name.startswith("tsconfig"):
            return "ts"
        if name in (".gitignore", ".editorconfig", ".env.example"):
            return "config"
        if name.startswith("docker"):
            return "docker"
        return "root"

    # Multi-level paths
    top = parts[0].lower()
    if top == "docs":
        if len(parts) > 2:
            return f"docs/{parts[1]}"
        return "docs"
    if top == "scripts":
        return "scripts"
    if top == ".github":
        return "ci"

    if top in ("apps", "packages", "services"):
        # e.g. apps/web/src/components/ui/button.tsx
        sub = parts[1] if len(parts) > 1 else top
        if len(parts) >= 4 and parts[2] == "src":
            category = parts[3] # components, app, lib, hooks, server, api
            if category == "components":
                return f"{sub}/ui"
            elif category == "app" or category == "pages":
                if len(parts) >= 5:
                    return f"{sub}/{parts[4]}"
                return f"{sub}/pages"
            elif category in ("api", "routes"):
                return f"{sub}/api"
            elif category in ("hooks", "stores", "utils", "lib", "services", "db"):
                return f"{sub}/{category}"
            return f"{sub}/{category}"
        return sub

    # Default fallback to parent folder name
    return parts[0]

def infer_commit_message(status, file_path, orig_path=None):
    """
    Generate conventional commit message broken down atomically.
    Format: <type>(<scope>): <subject>
    """
    scope = infer_scope(file_path)
    p = Path(file_path)
    basename = p.name
    stem = p.stem
    ext = p.suffix.lower()

    # Determine type
    is_doc = ext in (".md", ".mdx", ".txt", ".rst") or "docs" in p.parts
    is_test = re.search(r"(\.test\.|\.spec\.|__tests__|/tests?/)", file_path) is not None
    is_style = ext in (".css", ".scss", ".sass", ".less") or "tailwind" in basename.lower()
    is_ci = ".github" in p.parts or "ci" in basename.lower()
    is_config = basename in (
        "package.json", "tsconfig.json", "pnpm-lock.yaml", "pnpm-workspace.yaml",
        "vite.config.ts", "next.config.js", "next.config.mjs", "next.config.ts",
        "postcss.config.js", "tailwind.config.ts", "tailwind.config.js",
        ".gitignore", ".eslintrc.json", ".prettierrc", "Dockerfile", "docker-compose.yml"
    )

    action = "update"
    is_new = status in ("??", "A")
    is_deleted = "D" in status
    is_renamed = "R" in status

    # 1. Type determination
    if is_ci:
        commit_type = "ci"
    elif is_doc:
        commit_type = "docs"
    elif is_test:
        commit_type = "test"
    elif is_style:
        commit_type = "style"
    elif is_config or "scripts" in p.parts:
        commit_type = "chore"
    elif is_new:
        commit_type = "feat"
    elif is_deleted or is_renamed:
        commit_type = "refactor"
    else:
        commit_type = "feat"  # default for new app logic, can adjust to refactor/fix

    # 2. Subject determination
    if is_renamed and orig_path:
        subject = f"rename {orig_path} to {basename}"
        return f"refactor({scope}): {subject}"

    if is_deleted:
        subject = f"remove {basename}"
        return f"{commit_type if commit_type != 'feat' else 'refactor'}({scope}): {subject}"

    # Check for specific component/hook/page types
    item_kind = ""
    clean_name = stem
    if "component" in str(p.parent).lower() or ext in (".tsx", ".jsx"):
        item_kind = "component"
    elif "hook" in str(p.parent).lower() or stem.startswith("use"):
        item_kind = "hook"
    elif "api" in str(p.parent).lower() or basename in ("route.ts", "route.js"):
        item_kind = "endpoint"
        # use parent folder as name, e.g. api/auth/login -> login endpoint
        clean_name = p.parent.name
    elif basename in ("page.tsx", "page.jsx", "page.js"):
        item_kind = "page"
        clean_name = p.parent.name
    elif "schema" in basename.lower() or "model" in basename.lower():
        item_kind = "schema"
    elif "service" in basename.lower():
        item_kind = "service"

    if is_new:
        if is_doc:
            subject = f"add {basename} documentation"
        elif is_test:
            subject = f"add unit tests for {clean_name}"
        elif is_config:
            subject = f"initial configuration for {basename}"
        elif item_kind:
            subject = f"implement {clean_name} {item_kind}"
        else:
            subject = f"create {basename}"
    else:
        # Modified file: inspect diff for hints
        diff_text, _, _ = run_cmd(["git", "diff", "--", file_path], check=False)
        diff_lower = diff_text.lower()

        if "fix" in diff_lower or "bug" in diff_lower or "error" in diff_lower:
            commit_type = "fix"
            subject = f"fix issue in {basename}"
        elif is_doc:
            subject = f"update {basename}"
        elif is_config:
            subject = f"update {basename} settings"
        elif is_test:
            subject = f"update tests in {basename}"
        elif is_style:
            subject = f"refine styles in {basename}"
        else:
            commit_type = "refactor" if not is_new else "feat"
            if item_kind:
                subject = f"update {clean_name} {item_kind}"
            else:
                subject = f"update {basename}"

    # Check if a specific function was modified via hunk header
    hunk_match = re.search(r"@@.*@@\s+(?:function|def|class|const|async function)\s+([a-zA-Z0-9_]+)", diff_text if not is_new else "")
    if hunk_match and hunk_match.group(1):
        target_symbol = hunk_match.group(1)
        subject = f"{'add' if is_new else 'update'} {target_symbol} in {basename}"

    return f"{commit_type}({scope}): {subject}"

def commit_and_push_file(status, file_path, orig_path=None):
    """Stage a single file, commit it semantically, and push."""
    msg = infer_commit_message(status, file_path, orig_path)
    print(f"\n[AUTO-COMMIT] Staging file: {file_path}")

    # Stage specifically this file
    if "R" in status and orig_path:
        run_cmd(["git", "add", "--", orig_path, file_path])
    elif "D" in status:
        run_cmd(["git", "rm", "--cached", "--ignore-unmatch", "--", file_path])
        # In case file is also deleted in working tree
        run_cmd(["git", "add", "-u", "--", file_path])
    else:
        run_cmd(["git", "add", "--", file_path])

    # Check if there is anything staged
    diff_staged, _, _ = run_cmd(["git", "diff", "--staged", "--name-only"], check=False)
    if not diff_staged:
        print(f"  -> Nothing staged for {file_path}, skipping.")
        return False

    env = {
        "GIT_AUTHOR_NAME": GIT_AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": GIT_AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": GIT_AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": GIT_AUTHOR_EMAIL,
    }

    print(f"  -> Commit: {msg}")
    run_cmd(["git", "commit", "-m", msg], env=env)
    return True

def push_to_remote():
    """Push local commits to origin on the current branch with retry logic."""
    branch = get_current_branch()
    print(f"[AUTO-PUSH] Pushing commits to origin/{branch}...")
    try:
        run_cmd(["git", "push", "origin", branch])
        print(f"[AUTO-PUSH] Successfully pushed to origin/{branch}!")
        return True
    except RuntimeError as e:
        print(f"[AUTO-PUSH] Push failed, attempting pull --rebase before retrying... ({e})")
        try:
            run_cmd(["git", "pull", "--rebase", "origin", branch])
            run_cmd(["git", "push", "origin", branch])
            print(f"[AUTO-PUSH] Rebase & Push succeeded!")
            return True
        except Exception as retry_err:
            print(f"[AUTO-PUSH ERROR] Could not push: {retry_err}")
            return False

def process_all_changes():
    """Inspect changes and commit each one granularly."""
    ensure_git_config()
    items = get_git_status()
    if not items:
        return 0

    print(f"\n[DAEMON] Detected {len(items)} changed item(s). Decomposing into atomic commits...")
    committed_count = 0

    for status, file_path, orig_path in items:
        # Ignore untracked unwanted files
        if is_ignored(file_path):
            continue
        try:
            if commit_and_push_file(status, file_path, orig_path):
                committed_count += 1
        except Exception as err:
            print(f"[ERROR] Failed committing {file_path}: {err}")

    if committed_count > 0:
        push_to_remote()

    return committed_count

def watch_loop(poll_interval=3, settle_delay=2):
    """
    Continuous monitoring loop.
    settle_delay: wait seconds after change detection to allow active agent/editor writes to finish.
    """
    print("=" * 65)
    print("  UNJOBLESS AUTO-COMMIT & PUSH DAEMON STARTED")
    print(f"  Author/Committer : {GIT_AUTHOR_NAME} <{GIT_AUTHOR_EMAIL}>")
    print(f"  Branch           : {get_current_branch()}")
    print(f"  Polling interval : {poll_interval}s (debounce: {settle_delay}s)")
    print("  Granularity      : Atomic (file-by-file semantic commits)")
    print("=" * 65)

    last_sig = ""
    while True:
        try:
            items = get_git_status()
            current_sig = "|".join(f"{s}:{f}" for s, f, _ in items)

            if items:
                # If changes are detected, wait debounce time to let Claude Code finish writing
                time.sleep(settle_delay)
                # Re-check status after settling
                items_after = get_git_status()
                process_all_changes()
            else:
                pass
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[DAEMON] Stopping watcher gracefully...")
            break
        except Exception as e:
            print(f"[DAEMON EXCEPTION] {e}")
            time.sleep(poll_interval)

def main():
    parser = argparse.ArgumentParser(description="Unjobless Atomic Auto-Commit & Push")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no loop)")
    parser.add_argument("--interval", type=int, default=3, help="Polling interval in seconds")
    parser.add_argument("--settle", type=int, default=2, help="Debounce settle delay in seconds")
    args = parser.parse_args()

    if args.once:
        process_all_changes()
    else:
        watch_loop(poll_interval=args.interval, settle_delay=args.settle)

if __name__ == "__main__":
    main()
