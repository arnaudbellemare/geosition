#!/usr/bin/env python3
"""Install the pre-push check without replacing an existing hook."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


hook = Path(subprocess.check_output(["git", "rev-parse", "--git-path", "hooks/pre-push"], text=True).strip())
try:
    with hook.open("x", encoding="utf-8") as output:
        output.write('#!/bin/sh\nexec python3 scripts/pre-push-check.py\n')
except FileExistsError:
    print(f"An existing hook was not replaced: {hook}", file=sys.stderr)
    raise SystemExit(1)
os.chmod(hook, 0o755)
print(f"Installed {hook}")
