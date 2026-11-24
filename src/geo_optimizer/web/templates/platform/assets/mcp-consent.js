'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const authorizationId = new URLSearchParams(location.search).get('authorization_id');
  const sections = ['workspace-signin', 'identity-signin', 'review'];
  const show = (id) => sections.forEach((name) => { $(name).hidden = name !== id; });
  const message = (text) => { $('message').textContent = text || ''; };
  const csrf = () => {
    const item = document.cookie.split('; ').find((part) => part.startsWith('geo_csrf='));
    return item ? decodeURIComponent(item.slice('geo_csrf='.length)) : '';
  };
  async function api(path, body) {
    const options = body === undefined ? {cache: 'no-store'} : {
      method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json', 'x-csrf-token': csrf()},
      body: JSON.stringify(body),
    };
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong. Try again.');
    return data;
  }
  async function currentWorkspace() {
    const data = await api('/api/v1/workspaces');
    const current = data.workspaces.find((item) => item.org_id === data.current_org_id);
    if (!current) throw new Error('Choose a workspace before connecting.');
    $('active-workspace').textContent = current.name;
    show('identity-signin');
  }
  function busy(form, value) {
    form.querySelectorAll('button').forEach((button) => { button.disabled = value; });
  }
  $('workspace-form').addEventListener('submit', async (event) => {
    event.preventDefault(); message(''); busy(event.currentTarget, true);
    try {
      await api('/api/v1/auth/login', {email: $('workspace-email').value, password: $('workspace-password').value});
      $('workspace-password').value = '';
      await currentWorkspace();
    } catch (error) { message(error.message); }
    finally { busy(event.currentTarget, false); }
  });
  $('identity-form').addEventListener('submit', async (event) => {
    event.preventDefault(); message(''); busy(event.currentTarget, true);
    try {
      await api('/api/v1/mcp/consent/provider-login', {
        email: $('identity-email').value, password: $('identity-password').value,
      });
      $('identity-password').value = '';
      const review = await api('/api/v1/mcp/consent/review', {authorization_id: authorizationId});
      $('client-name').textContent = review.client_name;
      $('review-workspace').textContent = review.workspace_name;
      $('provider-scopes').textContent = review.provider_scopes || 'None specified';
      $('redirect-host').textContent = new URL(review.redirect_uri).hostname;
      show('review');
    } catch (error) { message(error.message); }
    finally { busy(event.currentTarget, false); }
  });
  async function decide(decision) {
    message(''); busy($('consent-form'), true);
    try {
      const permissions = ['permission-read', 'permission-write'].filter((id) => $(id).checked).map((id) => $(id).value);
      const result = await api('/api/v1/mcp/consent/decision', {decision, permissions});
      location.assign(result.redirect_url);
    } catch (error) { message(error.message); busy($('consent-form'), false); }
  }
  $('consent-form').addEventListener('submit', (event) => { event.preventDefault(); decide('approve'); });
  $('deny').addEventListener('click', () => decide('deny'));
  if (!authorizationId || !/^[A-Za-z0-9_-]{1,128}$/.test(authorizationId)) {
    message('This connection request is missing or expired. Start again from your AI service.');
  } else {
    currentWorkspace().catch(() => { show('workspace-signin'); });
  }
})();
