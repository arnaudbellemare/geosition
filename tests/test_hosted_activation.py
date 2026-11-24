from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
import geo_optimizer


def test_explicit_hosted_activation_fails_closed_without_persistent_storage(tmp_path):
    env = os.environ.copy()
    for name in ('SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SECRET_KEY',
                 'SUPABASE_SERVICE_ROLE_KEY', 'VERCEL'):
        env.pop(name, None)
    env.update({'GEOSITION_HOSTED_MCP_ENABLED': '1', 'GEO_PLATFORM_DB': str(tmp_path / 'platform.db')})
    source = str(Path(geo_optimizer.__file__).resolve().parent.parent)
    code = 'import sys; sys.path.insert(0, sys.argv[1]); import geo_optimizer.web.app'
    result = subprocess.run([sys.executable, '-c', code, source], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Hosted MCP requires persistent Supabase platform storage' in result.stderr
