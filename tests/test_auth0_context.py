from datetime import datetime, timedelta, timezone
import pytest

jwt = pytest.importorskip('jwt')

from geo_optimizer.mcp.auth0_context import verify_action_context

SECRET = 'a-very-long-testing-key-that-is-not-a-production-secret'
ISSUER = 'pilot.us.auth0.com'
RESOURCE = 'https://www.geositionai.com/mcp'

def signed(**updates):
    now = datetime.now(timezone.utc)
    payload = {'iss': ISSUER, 'sub': 'auth0|mom', 'iat': now,
               'exp': now + timedelta(seconds=60), 'client_id': 'chatgpt',
               'resource': RESOURCE, 'purpose': 'workspace-link'}
    payload.update(updates)
    return jwt.encode(payload, SECRET, algorithm='HS256')

def test_accepts_only_verified_known_client_context():
    result = verify_action_context(signed(), secret=SECRET, issuer=ISSUER,
                                   resource=RESOURCE, clients={'chatgpt': 'ChatGPT'})
    assert result.subject == 'auth0|mom'
    assert result.client_name == 'ChatGPT'

@pytest.mark.parametrize('changes', [
    {'iss': 'attacker.example'}, {'resource': 'https://other.example/mcp'},
    {'client_id': 'unknown'}, {'purpose': 'other'}, {'sub': ''},
    {'exp': datetime.now(timezone.utc) - timedelta(seconds=10)},
])
def test_rejects_invalid_or_unapproved_action_context(changes):
    with pytest.raises(PermissionError):
        verify_action_context(signed(**changes), secret=SECRET, issuer=ISSUER,
                              resource=RESOURCE, clients={'chatgpt': 'ChatGPT'})

def test_rejects_a_tampered_signature_and_long_lived_context():
    token = signed()
    first, second, signature = token.split('.')
    forged = '.'.join((first, second, ('A' if signature[0] != 'A' else 'B') + signature[1:]))
    now = datetime.now(timezone.utc)
    for invalid in (forged, signed(exp=now + timedelta(hours=1))):
        with pytest.raises(PermissionError):
            verify_action_context(invalid, secret=SECRET, issuer=ISSUER,
                                  resource=RESOURCE, clients={'chatgpt': 'ChatGPT'})


def test_recognizable_identity_comes_from_signed_context():
    result = verify_action_context(signed(email='owner@example.test', email_verified=True), secret=SECRET,
                                   issuer=ISSUER, resource=RESOURCE, clients={'chatgpt': 'ChatGPT'})
    assert result.email == 'owner@example.test'
    assert result.email_verified is True
    with pytest.raises(PermissionError):
        verify_action_context(signed(email_verified='yes'), secret=SECRET, issuer=ISSUER,
                              resource=RESOURCE, clients={'chatgpt': 'ChatGPT'})
