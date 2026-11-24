from __future__ import annotations

import json
from unittest.mock import patch

from geo_optimizer.mcp.server import geo_commerce_audit
from geo_optimizer.models.results.commerce_site import CommerceSiteReport


def test_commerce_tool_reports_bounded_audit_and_rejects_invalid_inputs():
    report = CommerceSiteReport(url='https://example.com/', coverage={'pages_audited': 1}, recommendations=[{'title': 'Review'}])
    with patch('geo_optimizer.utils.validators.validate_public_url', return_value=(True, None)), patch('geo_optimizer.core.commerce_site.run_site_audit', return_value=report):
        result = json.loads(geo_commerce_audit('example.com', 2))
        assert result['coverage']['pages_audited'] == 1
        assert result['recommendations'][0]['title'] == 'Review'
        assert 'error' in json.loads(geo_commerce_audit('example.com', 11))
    assert 'Unsafe URL' in json.loads(geo_commerce_audit('http://127.0.0.1/'))['error']
