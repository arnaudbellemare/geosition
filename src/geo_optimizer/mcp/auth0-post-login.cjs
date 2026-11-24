/** Auth0 Post-Login Action. Configure the two secrets shown below in Auth0. */
exports.onExecutePostLogin = async (event, api) => {
  const resource = 'https://www.geositionai.com/mcp';
  if (event.resource_server?.identifier !== resource) return;
  if (!event.client?.client_id || !event.user?.user_id) {
    return api.access.deny('The connection request is incomplete.');
  }
  const token = api.redirect.encodeToken({
    secret: event.secrets.GEOSITION_REDIRECT_SECRET,
    expiresInSeconds: 60,
    payload: {client_id: event.client.client_id, resource, purpose: 'workspace-link',
              email: event.user.email || '', email_verified: event.user.email_verified === true},
  });
  api.redirect.sendUserTo('https://www.geositionai.com/oauth/auth0/start', {
    query: {session_token: token},
  });
};

exports.onContinuePostLogin = async (event, api) => {
  const resource = 'https://www.geositionai.com/mcp';
  try {
    const result = api.redirect.validateToken({secret: event.secrets.GEOSITION_REDIRECT_SECRET,
                                                tokenParameterName: 'session_token'});
    if (result.decision !== 'approve' || result.sub !== event.user.user_id ||
        result.client_id !== event.client.client_id || result.resource !== resource ||
        result.iss !== resource || event.resource_server?.identifier !== resource) {
      return api.access.deny('Workspace access was not approved.');
    }
  } catch (_) {
    return api.access.deny('Workspace access could not be verified.');
  }
};
