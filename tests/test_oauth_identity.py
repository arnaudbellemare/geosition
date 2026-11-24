from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

jwt = pytest.importorskip('jwt', reason='Install the MCP extra to test OAuth tokens')

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant, WorkspaceTokenVerifier

ISSUER = 'https://identity.example.test/auth/v1'
AUDIENCE = 'https://geosition.example.test/mcp'


def test_pilot_oauth_grants_isolate_workspaces_and_recheck_membership():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    grants = {
        ('mom-sub', 'chatgpt', 10): WorkspaceGrant(ISSUER, 'mom-sub', 'chatgpt', 1, 10, frozenset({'setup:read'})),
        ('velora-sub', 'claude', 20): WorkspaceGrant(ISSUER, 'velora-sub', 'claude', 2, 20, frozenset({'setup:read'})),
    }
    members = {(1, 10), (2, 20)}
    verifier = WorkspaceTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, signing_key=lambda token: private_key.public_key(),
        find_grant=lambda issuer, subject, client, workspace: grants.get((subject, client, workspace)),
        is_member=lambda user, workspace: (user, workspace) in members,
    )

    def token(subject, client, **overrides):
        payload = {'iss': ISSUER, 'aud': AUDIENCE, 'sub': subject, 'client_id': client,
                   'iat': now, 'exp': now + timedelta(minutes=5)}
        payload.update(overrides)
        return jwt.encode(payload, private_key, algorithm='RS256')

    mom = token('mom-sub', 'chatgpt')
    velora = token('velora-sub', 'claude')
    assert verifier.authorize(mom, 10, 'setup:read').user_id == 1
    assert verifier.authorize(velora, 20, 'setup:read').user_id == 2
    for bearer, workspace, permission in [(mom, 20, 'setup:read'), (velora, 10, 'setup:read'),
                                           (mom, 10, 'setup:write'), (token('mom-sub', 'claude'), 10, 'setup:read')]:
        with pytest.raises(PermissionError):
            verifier.authorize(bearer, workspace, permission)
    for bearer in [token('mom-sub', 'chatgpt', aud='https://other.example.test'),
                   token('mom-sub', 'chatgpt', iss='https://other.example.test'),
                   token('mom-sub', 'chatgpt', exp=now - timedelta(seconds=1)),
                   jwt.encode({'sub': 'mom-sub'}, 'wrong-secret-for-test-only-32-bytes', algorithm='HS256')]:
        with pytest.raises(PermissionError):
            verifier.authorize(bearer, 10, 'setup:read')
    members.remove((1, 10))
    with pytest.raises(PermissionError):
        verifier.authorize(mom, 10, 'setup:read')
    members.add((1, 10))
    grants[('mom-sub', 'chatgpt', 10)] = grants[('velora-sub', 'claude', 20)]
    with pytest.raises(PermissionError):
        verifier.authorize(mom, 10, 'setup:read')
    grants[('mom-sub', 'chatgpt', 10)] = WorkspaceGrant(
        ISSUER, 'mom-sub', 'chatgpt', 1, 10, frozenset({'setup:read'}), active=False)
    with pytest.raises(PermissionError):
        verifier.authorize(mom, 10, 'setup:read')
