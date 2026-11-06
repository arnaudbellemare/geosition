#!/usr/bin/env python3
"""Run the same checks on files changed by the refs being pushed."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    files: set[str] = set()
    for line in sys.stdin:
        _local_ref, local_sha, _remote_ref, remote_sha = line.split()
        if not int(local_sha, 16):
            continue
        if int(remote_sha, 16):
            base = remote_sha
        else:
            base = subprocess.check_output(["git", "hash-object", "-t", "tree", "/dev/null"], text=True).strip()
        diff = subprocess.check_output(
            ["git", "diff", "--name-only", "-z", "--diff-filter=ACMR", base, local_sha]
        )
        files.update(name for name in diff.decode("utf-8").split("\0") if name)
    if not files:
        print("No changed files to check.")
        return 0
    return subprocess.call(["pre-commit", "run", "--files", *sorted(files)])


if __name__ == "__main__":
    raise SystemExit(main())
