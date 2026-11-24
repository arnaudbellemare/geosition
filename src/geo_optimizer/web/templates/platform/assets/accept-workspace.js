(() => {
  const token = decodeURIComponent(location.hash.slice(1));
  history.replaceState(null, '', location.pathname);
  const result = document.getElementById('result');
  document.getElementById('accept').addEventListener('click', async event => {
    const csrf = document.cookie.split('; ').find(item => item.startsWith('geo_csrf='));
    event.currentTarget.disabled = true;
    try {
      const response = await fetch('/api/v1/workspace/invitations/accept', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ? decodeURIComponent(csrf.slice(9)) : '' }, body: JSON.stringify({ token }) });
      const body = await response.json();
      if (!response.ok) throw new Error(response.status === 401 ? 'Sign in with the invited email, then return here and try again.' : body.detail || 'Could not accept the invitation.');
      result.textContent = 'Invitation accepted. Opening the shared workspace…';
      location.assign('/platform/dashboard');
    } catch (error) { result.textContent = error.message; event.currentTarget.disabled = false; }
  });
})();
