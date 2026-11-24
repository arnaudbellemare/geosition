from __future__ import annotations

from unittest.mock import Mock

import pytest

from geo_optimizer.mcp.supabase_oauth_provider import SupabaseOAuthProvider


def test_supabase_provider_fetches_user_and_pending_consent_without_redirects():
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'provider-user'}
    request = Mock(return_value=response)
    provider = SupabaseOAuthProvider('https://project.supabase.co', 'sb_publishable_test',
                                     'https://www.geositionai.com', request=request)
    assert provider.get_user('test-session')['id'] == 'provider-user'
    assert request.call_args.args[:2] == ('GET', 'https://project.supabase.co/auth/v1/user')
    assert request.call_args.kwargs['allow_redirects'] is False
    assert request.call_args.kwargs['headers']['Origin'] == 'https://www.geositionai.com'
    provider.get_authorization_details('test-session', 'auth-123')
    assert request.call_args.args[1].endswith('/oauth/authorizations/auth-123')
    provider.decide('test-session', 'auth-123', 'approve')
    assert request.call_args.kwargs['json'] == {'action': 'approve'}
    assert request.call_args.args[1].endswith('/oauth/authorizations/auth-123/consent')
    with pytest.raises(ValueError):
        provider.get_authorization_details('test-session', '../../user')
    with pytest.raises(ValueError):
        SupabaseOAuthProvider('https://project.supabase.co', 'sb_secret_test', 'https://www.geositionai.com')


def test_supabase_provider_rejects_invalid_session_and_unexpected_redirect():
    request = Mock(return_value=Mock(status_code=401))
    provider = SupabaseOAuthProvider('https://project.supabase.co', 'sb_publishable_test',
                                     'https://www.geositionai.com', request=request)
    with pytest.raises(PermissionError):
        provider.get_user('invalid')
    request.return_value.status_code = 302
    with pytest.raises(ValueError):
        provider.get_user('invalid')
