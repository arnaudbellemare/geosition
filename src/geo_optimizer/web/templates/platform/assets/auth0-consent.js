'use strict';
(() => {
  const el = (id) => document.getElementById(id);
  const csrf = () => decodeURIComponent((document.cookie.split('; ').find((x) => x.startsWith('geo_csrf=')) || '').slice(9));
  const show = (id) => ['sign-in', 'review'].forEach((name) => { el(name).hidden = name !== id; });
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
      method: 'POST', cache: 'no-store', headers: {'Content-Type':'application/json', 'x-csrf-token':csrf()},
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Unable to continue. Please try again.');
    return data;
  }
  async function review() {
    const data = await api('/api/v1/mcp/auth0/review');
    el('workspace').textContent = data.workspace;
    el('client').textContent = data.client;
    el('identity').textContent = data.email ? `${data.email} (${data.email_verified ? 'verified' : 'not verified'})` : data.identity;
    show('review');
  }
  const error = (err) => { el('message').textContent = err.message; };
  el('login').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('/api/v1/auth/login', {email:el('email').value, password:el('password').value});
      el('password').value = '';
      await review();
    } catch (err) { error(err); }
  });
  async function decide(decision) {
    try {
      const permissions = [];
      if (el('read').checked) permissions.push('setup:read');
      if (el('write').checked) permissions.push('setup:write');
      const result = await api('/api/v1/mcp/auth0/decision', {decision, permissions});
      const form = document.createElement('form');
      form.method = 'POST'; form.action = `${result.continue_url}?state=${encodeURIComponent(result.state)}`;
      for (const [name, value] of [['state', result.state], ['session_token', result.token]]) {
        const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value;
        form.appendChild(input);
      }
      document.body.appendChild(form); form.submit();
    } catch (err) { error(err); }
  }
  el('approve').addEventListener('submit', (event) => { event.preventDefault(); decide('approve'); });
  el('deny').addEventListener('click', () => decide('deny'));
  review().catch(() => show('sign-in'));
})();
