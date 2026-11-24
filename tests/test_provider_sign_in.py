from unittest.mock import Mock

import pytest

from geo_optimizer.mcp.supabase_oauth_provider import SupabaseOAuthProvider


def test_identity_sign_in_returns_only_access_token_and_rejects_failure():
    response = Mock(status_code=200)
    response.json.return_value = {'access_token': 'access', 'refresh_token': 'refresh'}
    request = Mock(return_value=response)
    provider = SupabaseOAuthProvider('https://project.supabase.co', 'sb_publishable_test',
                                     'https://www.geositionai.com', request=request)
    assert provider.sign_in('owner@example.test', 'password') == 'access'
    assert request.call_args.args[1] == 'https://project.supabase.co/auth/v1/token?grant_type=password'
    assert request.call_args.kwargs['allow_redirects'] is False
    response.status_code = 400
    with pytest.raises(PermissionError, match='sign-in failed'):
        provider.sign_in('owner@example.test', 'password')
