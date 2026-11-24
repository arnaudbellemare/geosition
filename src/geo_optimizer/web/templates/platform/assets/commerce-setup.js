(() => {
  'use strict';
  const steps = [
    { id: 'journey', title: 'Describe your customer journey', detail: 'Choose what a customer should be able to discover, compare, and do next on your website. Gather the website address and the right business contact.', owner: 'You and your GEOSITION operator' },
    { id: 'catalog', title: 'Prepare your product information', detail: 'Gather your authorized product names, images, prices, availability, and product page links. Demo items must stay clearly labeled and must not be submitted as real inventory.', owner: 'You and your GEOSITION operator', kind: ['products', 'both'], url: 'https://developers.openai.com/commerce/guides/submit-product-feeds', link: 'Read product feed guidance' },
    { id: 'service', title: 'Prepare your services and enquiry path', detail: 'Gather service descriptions, areas served, availability, and a working way for customers to enquire or book. Confirm who receives enquiries.', owner: 'You and your GEOSITION operator', kind: ['services', 'both'] },
    { id: 'site', title: 'Review the website', detail: 'Review representative pages, contact or checkout steps, and whether supported AI browsers can access the site. Record anything that needs a person to investigate.', owner: 'GEOSITION operator', url: 'https://developers.openai.com/commerce/agent-access', link: 'Read browser access guidance' },
    { id: 'accounts', title: 'Set up the required accounts', detail: 'The account owner signs in and approves any access. Depending on your chosen journey, you may need an OpenAI account and a payment provider’s test account. Never share passwords or keys in this page.', owner: 'Account owner', url: 'https://platform.openai.com/', link: 'Open OpenAI Platform' },
    { id: 'connection', title: 'Connect the customer journey', detail: 'Your operator checks the supported path for your business. A website handoff and a private ChatGPT connector are separate connections; neither is established by marking this step complete.', owner: 'Account owner and GEOSITION operator', url: 'https://developers.openai.com/commerce/guides/build-a-plugin', link: 'Read connection guidance' },
    { id: 'test', title: 'Test with no real transaction', detail: 'Walk through discovery and the handoff. For payments, use a provider test account and its test cards. Confirm the result with the business; do not treat a simulated test as a live connection.', owner: 'You and your GEOSITION operator' },
    { id: 'monitor', title: 'Plan ongoing checks', detail: 'Agree who will monitor changes, investigate failures, renew access, and review catalog or service information. Scheduling is not enabled by this checklist.', owner: 'You and your GEOSITION operator' }
  ];
  const form = document.getElementById('business-form');
  const business = document.getElementById('business');
  const kind = document.getElementById('kind');
  const domain = document.getElementById('domain');
  const auditResult = document.getElementById('audit-result');
  const plan = document.getElementById('plan');
  const output = document.getElementById('steps');
  const saved = document.getElementById('saved');
  let currentDomain = '';
  let statuses = {};
  let providers = [];
  const stateLabels = { todo: 'Not started', working: 'In progress', done: 'Marked complete by you', blocked: 'Needs help' };
  function headers() {
    const csrf = document.cookie.split('; ').find(item => item.startsWith('geo_csrf='));
    return { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ? decodeURIComponent(csrf.slice(9)) : '' };
  }
  async function api(url, options = {}) {
    const res = await fetch(url, { ...options, headers: headers() });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || 'Could not complete this request.');
    return body;
  }
  async function loadWorkspaces() {
    const select = document.getElementById('workspace-select');
    try {
      const data = await api('/api/v1/workspaces'); select.replaceChildren();
      for (const workspace of data.workspaces) {
        const option = document.createElement('option'); option.value = workspace.org_id; option.textContent = workspace.name;
        option.selected = workspace.org_id === data.current_org_id; select.append(option);
      }
    } catch (error) { select.replaceChildren(); saved.textContent = 'Sign in to your workspace to continue.'; }
  }
  document.getElementById('workspace-select').addEventListener('change', async event => {
    try {
      await api('/api/v1/workspaces/select', { method: 'POST', body: JSON.stringify({ org_id: Number(event.target.value) }) });
      plan.hidden = true; currentDomain = ''; saved.textContent = 'Workspace changed. Load your business plan.';
    } catch (error) { saved.textContent = error.message; await loadWorkspaces(); }
  });
  loadWorkspaces();
  function showAudit(audit) {
    auditResult.replaceChildren();
    if (!audit) return;
    const summary = document.createElement('p');
    summary.textContent = `Pages audited: ${audit.coverage.pages_audited}; failed: ${audit.failures.length}; skipped: ${audit.skipped.length}. ${audit.limitations}`;
    auditResult.append(summary);
    const list = document.createElement('ul');
    for (const rec of audit.recommendations) {
      const li = document.createElement('li'); li.textContent = `${rec.title}: ${rec.action}`; list.append(li);
    }
    auditResult.append(list);
    if (audit.browser_access) {
      const access = audit.browser_access;
      const title = document.createElement('h3'); title.textContent = 'ChatGPT cloud-browser access: not verified';
      const explanation = document.createElement('p'); explanation.textContent = access.limitations;
      if (access.provider_evidence) {
        const item = access.provider_evidence; const summary = document.createElement('p');
        summary.textContent = `Historical operator-reported Vercel verified-agent correlation: ${item.page_url}, ${item.request_time}. ${item.limit}`;
        auditResult.append(summary);
      }
      const evidence = document.createElement('ul');
      for (const item of access.observations) { const li = document.createElement('li'); li.textContent = `${item.url}: ordinary fetch ${item.fetch_status}${item.http_status ? ` (HTTP ${item.http_status})` : ''}`; evidence.append(li); }
      const hints = document.createElement('p'); hints.textContent = `Possible provider: ${access.provider_hints.join(', ') || 'not identified'}. ${access.provider_hint_note}`;
      const guideTitle = document.createElement('h4'); guideTitle.textContent = 'Test and fix';
      const instructions = document.createElement('ol');
      for (const step of access.test_steps) { const li = document.createElement('li'); li.textContent = step; instructions.append(li); }
      const label = document.createElement('label'); label.textContent = 'Choose the confirmed CDN or firewall';
      const select = document.createElement('select');
      for (const name of Object.keys(access.guided_fixes)) { const option = document.createElement('option'); option.value = name; option.textContent = name === 'other' ? 'Other or unknown' : name; select.append(option); }
      select.value = 'other';
      const fix = document.createElement('p'); const update = () => { fix.textContent = access.guided_fixes[select.value]; }; select.addEventListener('change', update); update();
      label.append(select); const link = document.createElement('a'); link.href = access.guidance_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Open current OpenAI agent-access guidance ↗';
      auditResult.append(title, explanation, evidence, hints, guideTitle, instructions, label, fix, link);
    }
  }
  function renderProviders() {
    const target = document.getElementById('provider-paths'); target.replaceChildren();
    const selected = new Set([...form.querySelectorAll('input[name="provider"]:checked')].map(input => input.value));
    document.getElementById('openai-account').hidden = !selected.has('chatgpt');
    document.getElementById('stripe-account').hidden = kind.value === 'services';
    for (const provider of providers.filter(item => selected.has(item.id))) {
      const section = document.createElement('section'); section.className = 'panel';
      const title = document.createElement('h3'); title.textContent = provider.name;
      const summary = document.createElement('p'); summary.textContent = provider.summary;
      const date = document.createElement('p'); date.textContent = `Guidance reviewed ${provider.updated}.`;
      section.append(title, summary, date);
      for (const step of provider.steps.filter(item => item.kind.includes(kind.value))) {
        const article = document.createElement('article'); article.className = 'guide-step';
        const number = document.createElement('span'); number.className = 'number'; number.textContent = '•'; number.setAttribute('aria-hidden', 'true');
        const body = document.createElement('div');
        const name = document.createElement('h4'); name.textContent = step.title;
        const detail = document.createElement('p'); detail.textContent = step.detail;
        const link = document.createElement('a'); link.href = step.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `${step.link} ↗`;
        const label = document.createElement('label'); label.textContent = `Team progress for ${step.title}`;
        const select = document.createElement('select');
        for (const [value, text] of Object.entries(stateLabels)) { const option = document.createElement('option'); option.value = value; option.textContent = text; select.append(option); }
        select.value = Object.hasOwn(stateLabels, statuses[step.id]) ? statuses[step.id] : 'todo';
        select.addEventListener('change', async () => {
          const previous = statuses[step.id] || 'todo'; select.disabled = true;
          try { await api('/api/v1/commerce/setup/step', { method: 'POST', body: JSON.stringify({ domain: currentDomain, step: step.id, status: select.value }) });
            statuses[step.id] = select.value; saved.textContent = 'Provider progress saved to your workspace; it is not provider-verified.';
          } catch (error) { select.value = previous; saved.textContent = error.message; }
          finally { select.disabled = false; }
        });
        label.append(select); body.append(name, detail, link, label); article.append(number, body); section.append(article);
      }
      target.append(section);
    }
  }
  function render() {
    output.replaceChildren();
    const applicable = steps.filter(step => !step.kind || step.kind.includes(kind.value));
    document.getElementById('plan-title').textContent = `${business.value.trim()} setup plan`;
    applicable.forEach((step, index) => {
      const article = document.createElement('article'); article.className = 'guide-step';
      const number = document.createElement('span'); number.className = 'number'; number.textContent = String(index + 1); number.setAttribute('aria-hidden', 'true');
      const body = document.createElement('div'); const head = document.createElement('div'); head.className = 'step-head';
      const title = document.createElement('h3'); title.textContent = step.title;
      const state = document.createElement('span'); state.className = 'state'; state.textContent = stateLabels[statuses[step.id]] || stateLabels.todo;
      head.append(title, state); const detail = document.createElement('p'); detail.textContent = step.detail;
      const owner = document.createElement('p'); owner.textContent = `Who: ${step.owner}`; body.append(head, detail, owner);
      if (step.url) { const link = document.createElement('a'); link.href = step.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `${step.link} ↗`; body.append(link); }
      if (step.id === 'accounts' && kind.value !== 'services') { const link = document.createElement('a'); link.href = 'https://dashboard.stripe.com/register'; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Create or open a Stripe account for test mode ↗'; body.append(document.createElement('br'), link); }
      const label = document.createElement('label'); label.textContent = `Progress for ${step.title}`; const select = document.createElement('select');
      for (const [value, text] of Object.entries(stateLabels)) { const option = document.createElement('option'); option.value = value; option.textContent = text; select.append(option); }
      select.value = Object.hasOwn(stateLabels, statuses[step.id]) ? statuses[step.id] : 'todo';
      select.addEventListener('change', async () => {
        const previous = statuses[step.id] || 'todo'; select.disabled = true;
        try {
          await api('/api/v1/commerce/setup/step', { method: 'POST', body: JSON.stringify({ domain: currentDomain, step: step.id, status: select.value }) });
          statuses[step.id] = select.value; state.textContent = stateLabels[select.value]; saved.textContent = 'Progress saved to your workspace.';
        } catch (error) { select.value = previous; saved.textContent = error.message; }
        finally { select.disabled = false; }
      });
      label.append(select); body.append(label); article.append(number, body); output.append(article);
    });
    renderProviders();
    plan.hidden = false;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!form.reportValidity()) return;
    if (!form.querySelector('input[name="provider"]:checked')) { saved.textContent = 'Choose at least one AI service.'; return; }
    try {
      const result = await api(`/api/v1/commerce/setup?domain=${encodeURIComponent(domain.value.trim())}`);
      currentDomain = result.domain; statuses = result.statuses; providers = result.providers || []; saved.textContent = 'Workspace progress loaded.';
      render(); showAudit(result.audit);
      try {
        const connection = await api(`/api/v1/commerce/vercel?domain=${encodeURIComponent(currentDomain)}`);
        document.getElementById('vercel-status').textContent = connection.connected ? `Saved Vercel connection for project ${connection.project_id}. Current access and browser access have not been verified.` : 'No Vercel connection saved.';
      } catch (error) {
        document.getElementById('vercel-status').textContent = 'Vercel connection status is unavailable. Ask your GEOSITION administrator for help.';
      }
    } catch (error) { plan.hidden = true; saved.textContent = error.message; }
  });
  document.getElementById('vercel-form').addEventListener('submit', async event => {
    event.preventDefault(); const status = document.getElementById('vercel-status');
    try {
      const result = await api('/api/v1/commerce/vercel/start', {method: 'POST', body: JSON.stringify({domain: currentDomain, project: document.getElementById('vercel-project').value.trim(), team_slug: document.getElementById('vercel-team').value.trim()})});
      window.location.assign(result.authorization_url);
    } catch (error) { status.textContent = error.message; }
  });
  document.getElementById('vercel-disconnect').addEventListener('click', async () => {
    const status = document.getElementById('vercel-status');
    try {
      await api('/api/v1/commerce/vercel/disconnect', {method: 'POST', body: JSON.stringify({domain: currentDomain})});
      status.textContent = 'Saved connection removed. Also remove the integration in Vercel to revoke access.';
    } catch (error) { status.textContent = error.message; }
  });
  if (new URLSearchParams(location.search).has('vercel')) {
    const status = new URLSearchParams(location.search).get('vercel');
    if (status === 'confirm') {
      api('/api/v1/commerce/vercel/pending').then(data => {
        const section = document.getElementById('vercel-confirm');
        section.hidden = false; plan.hidden = false;
        document.getElementById('vercel-confirm-detail').textContent = `Confirm project ${data.project_id} for ${data.domain} (Vercel team ${data.team_id || 'personal'}).`;
        saved.textContent = 'Review the Vercel connection before saving it.';
      }).catch(error => { saved.textContent = error.message; });
    } else saved.textContent = status === 'connected' ? 'Vercel connected. Load your business plan to see the connection.' : 'Vercel connection failed. Load your plan and try again.';
    history.replaceState(null, '', location.pathname);
  }
  document.getElementById('vercel-confirm-button').addEventListener('click', async () => {
    try {
      const result = await api('/api/v1/commerce/vercel/confirm', {method: 'POST', body: '{}'});
      document.getElementById('vercel-confirm').hidden = true;
      saved.textContent = `Connected ${result.domain} to ${result.project_id}.`;
      window.location.assign(result.next_url);
    } catch (error) { saved.textContent = error.message; }
  });
  document.getElementById('invite-form').addEventListener('submit', async event => {
    event.preventDefault();
    const result = document.getElementById('invite-result');
    const label = document.getElementById('invite-link-label'); label.hidden = true;
    try {
      const invite = await api('/api/v1/workspace/invitations', { method: 'POST', body: JSON.stringify({ email: document.getElementById('invite-email').value }) });
      document.getElementById('invite-link').value = `${location.origin}/platform/static/accept-workspace.html#${encodeURIComponent(invite.token)}`;
      label.hidden = false; result.textContent = 'Link created. Share it privately with the named operator. It expires in seven days.';
    } catch (error) { result.textContent = error.message; }
  });
  document.getElementById('browser-evidence-form').addEventListener('submit', async event => {
    event.preventDefault(); const status = document.getElementById('browser-evidence-status');
    try {
      const evidence = JSON.parse(document.getElementById('browser-evidence').value);
      await api('/api/v1/commerce/setup/browser-evidence', { method: 'POST', body: JSON.stringify({domain: currentDomain, evidence}) });
      const setup = await api(`/api/v1/commerce/setup?domain=${encodeURIComponent(currentDomain)}`);
      showAudit(setup.audit); status.textContent = 'Evidence saved to this workspace. It is reported by your team and not independently verified.';
    } catch (error) { status.textContent = error instanceof SyntaxError ? 'Enter valid evidence JSON.' : error.message; }
  });
  document.getElementById('run-audit').addEventListener('click', async event => {
    const button = event.currentTarget; button.disabled = true; saved.textContent = 'Auditing your site…';
    try {
      const audit = await api('/api/v1/commerce/setup/audit', { method: 'POST', body: JSON.stringify({ domain: currentDomain }) });
      showAudit(audit); saved.textContent = 'Audit saved to your workspace.';
    } catch (error) { saved.textContent = error.message; }
    finally { button.disabled = false; }
  });
})();
