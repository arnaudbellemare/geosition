// Render prefetched HTML and scripts only. All browser-initiated requests are denied.
const fs = require('node:fs');
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd(), __dirname] }));
(async () => {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const executablePath = process.env.GEO_CHROMIUM_PATH || (fs.existsSync(chromium.executablePath()) ? chromium.executablePath() : undefined);
  const browser = await chromium.launch({ headless: true, executablePath, proxy: { server: 'http://127.0.0.1:9', bypass: '<-loopback>' }, args: ['--disable-quic', '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'] });
  try {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    await context.routeWebSocket('**/*', socket => socket.close());
    await context.route('**/*', async route => {
      const request = route.request();
      const url = request.url();
      if (request.method() === 'GET' && request.isNavigationRequest() && url === input.url) {
        return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: input.html });
      }
      if (request.method() === 'GET' && request.resourceType() === 'script' && Object.hasOwn(input.scripts, url)) {
        return route.fulfill({ status: 200, contentType: 'application/javascript; charset=utf-8', body: input.scripts[url] });
      }
      return route.abort();
    });
    const page = await context.newPage();
    await page.goto(input.url, { waitUntil: 'domcontentloaded', timeout: 12000 });
    await page.waitForTimeout(500);
    process.stdout.write(JSON.stringify({ html: await page.content() }));
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
