import { expect, test } from '@playwright/test';

function smokeEmail() {
  return `geosition-playwright+${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
}

async function registerWorkspace(request, baseURL) {
  const email = smokeEmail();
  const password = `SmokePass-${Math.random().toString(16).slice(2, 14)}`;
  const domain = `playwright-${Date.now()}.example.com`;
  const response = await request.post(`${baseURL}/api/v1/auth/register`, {
    data: {
      email,
      password,
      org_name: 'Playwright Smoke',
      domain,
    },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  return {
    email,
    password,
    domain,
    token: payload.session.token,
  };
}

test('locked dashboard keeps verification as the single current step and opens Skill Files', async ({ page, request, baseURL }) => {
  const workspace = await registerWorkspace(request, baseURL);
  await page.setExtraHTTPHeaders({ Authorization: `Bearer ${workspace.token}` });

  await page.goto('/platform/dashboard');
  await expect(page.locator('body')).toHaveClass(/workspace-locked/);
  await expect(page.getByText('Domain access required')).toBeVisible();
  await expect(page.locator('[data-product-step].is-current')).toHaveCount(1);
  await expect(page.locator('[data-product-step="verify"]')).toHaveClass(/is-current/);
  await expect(page.locator('#run-sitemap-audit')).toBeDisabled();

  await page.locator('#copy-skill-files').click();
  await expect(page.locator('#skill-files-modal')).toBeVisible();
  await expect(page.locator('[data-product-step].is-current')).toHaveCount(1);
  await expect(page.locator('[data-product-step="verify"]')).toHaveClass(/is-current/);
});

test('verified dashboard enables audit controls for a pre-verified smoke account', async ({ page, request, baseURL }) => {
  const email = process.env.GEOSITION_PLAYWRIGHT_VERIFIED_EMAIL;
  const password = process.env.GEOSITION_PLAYWRIGHT_VERIFIED_PASSWORD;
  const domain = process.env.GEOSITION_PLAYWRIGHT_VERIFIED_DOMAIN;
  test.skip(!email || !password || !domain, 'Set a pre-verified smoke account to run unlocked dashboard checks.');

  const login = await request.post(`${baseURL}/api/v1/auth/login`, {
    data: { email, password },
  });
  expect(login.ok()).toBeTruthy();
  const payload = await login.json();
  await page.setExtraHTTPHeaders({ Authorization: `Bearer ${payload.session.token}` });

  await page.goto('/platform/dashboard');
  await expect(page.locator('body')).not.toHaveClass(/workspace-locked/);
  await expect(page.locator('#run-audit')).toBeEnabled();
  await expect(page.locator('#run-sitemap-audit')).toBeEnabled();
  await expect(page.locator('#run-benchmark')).toBeEnabled();
  await expect(page.locator('[data-product-step].is-current')).toHaveCount(1);
  await expect(page.locator('#domain-input')).toHaveValue(domain);
});
