from unittest.mock import Mock, patch

from geo_optimizer.core.commerce_browser_access import build_browser_access, observe_fetch
from geo_optimizer.core.commerce_site import run_site_audit


def test_normal_success_and_challenge_never_verify_chatgpt_access():
    ok = observe_fetch('https://example.com/', Mock(status_code=200, headers={'Server': 'cloudflare'}), None)
    blocked = observe_fetch('https://example.com/shop', Mock(status_code=403, headers={'cf-mitigated': 'challenge'}), None)
    access = build_browser_access([ok, blocked])
    assert [item['fetch_status'] for item in access['observations']] == ['reachable', 'challenge_observed']
    assert access['verified_access'] == 'unknown'
    assert access['provider_hints'] == ['cloudflare']
    assert 'signature' in access['guided_fixes']['other'].lower()
    assert 'verified' in access['guided_fixes']['cloudflare'].lower()


def test_site_audit_records_ordinary_fetch_and_guided_fix():
    response = Mock(status_code=200, url='https://example.com/', text='<a href="/contact">Contact</a>', headers={'x-vercel-id': 'sample'})
    def fetch(url, **kwargs):
        return (response, None) if url == 'https://example.com/' else (None, 'not available')
    with patch('geo_optimizer.core.commerce_site.fetch_url', side_effect=fetch):
        report = run_site_audit('https://example.com/', max_pages=1)
    assert report.browser_access['verified_access'] == 'unknown'
    assert report.browser_access['observations'][0]['http_status'] == 200
    assert report.browser_access['provider_hints'] == ['vercel']
    assert any(rec['id'] == 'verify-browser-access' for rec in report.recommendations)
