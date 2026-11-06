#!/usr/bin/env python3
"""Check changed files without modifying the working tree."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    mode, *names = sys.argv[1:]
    for name in names:
        path = Path(name)
        if not path.is_file():
            continue
        if mode == "secrets":
            result = subprocess.run(
                ["gitleaks", "dir", "--no-banner", "--redact", "--exit-code", "1", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if result.returncode:
                print(f"Secret scan failed for {name}:\n{result.stderr}", file=sys.stderr)
                return result.returncode
        elif mode == "syntax":
            try:
                if path.suffix == ".py":
                    ast.parse(path.read_bytes(), filename=name)
                elif path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
                else:
                    command = ["bash", "-n", name] if path.suffix == ".sh" else ["node", "--check", name]
                    subprocess.run(command, check=True)
            except (SyntaxError, ValueError, UnicodeError, subprocess.CalledProcessError) as exc:
                print(f"Syntax check failed for {name}: {exc}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
