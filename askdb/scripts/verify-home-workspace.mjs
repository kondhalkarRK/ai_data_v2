import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
await context.addCookies([{ name: 'nql_access', value: 'synthetic-home-fixture', domain: 'localhost', path: '/' }]);
const page = await context.newPage();
const errors = [];
let state = 'populated';
let chatRequests = 0;
page.on('pageerror', error => errors.push(error.message));
const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) });
await page.route('**/*', async route => {
  const path = new URL(route.request().url()).pathname;
  if (path.endsWith('/auth/me')) return route.fulfill(json({ id: 'home-fixture', username: 'rahul', fullName: 'Rahul Demo', email: 'rahul@example.com', role: 'admin', defaultIndustry: 'automotive', regionAccess: { unrestricted: false, zones: ['West'], hideRegionFilter: false } }));
  if (path === '/ready') return route.fulfill(state === 'error' ? json({}, 503) : json({ status: state === 'degraded' ? 'degraded' : 'ready', checkedAt: '2026-11-10T08:00:00Z', dependencies: [{ name: 'Automotive warehouse', status: state === 'degraded' ? 'degraded' : 'ok', detail: 'Synthetic browser fixture', latencyMs: 12 }] }));
  if (path.endsWith('/industries')) return route.fulfill(state === 'error' ? json({}, 503) : json({ industries: [{ id: 'automotive', label: 'Automotive', databaseAvailable: state !== 'degraded', semanticPackLoaded: true, isDefault: true }] }));
  if (path.endsWith('/trust/center')) return route.fulfill(state === 'error' ? json({}, 503) : json({ dataAsOf: '2026-11-10T07:30:00Z', hero: { activeIncidents: state === 'degraded' ? 2 : 0 } }));
  if (path.endsWith('/questions')) return route.fulfill(state === 'error' ? json({}, 503) : json(state === 'empty' ? [] : [{ id: 'q1', title: 'Regional sales', question: 'Revenue by region', createdAt: '2026-11-09T10:00:00Z' }]));
  if (path.endsWith('/bi/capabilities')) return route.fulfill(json({ enabled: true, engine: 'askbi-v2', schemaVersion: 2 }));
  if (path.endsWith('/bi/reports')) return route.fulfill(state === 'error' ? json({}, 503) : json(state === 'empty' ? [] : [{ id: 'r1', title: 'CEO sales report', saved: true, revision: 1, state: { plan: null, previous: null, pending: null, turns: [], usage: {} } }]));
  if (path.endsWith('/trust/snapshot')) return route.fulfill(json({ available: false, score: null, label: 'Unavailable', components: [] }));
  if (path.endsWith('/chat/ask-sync')) { chatRequests++; return route.fulfill(json({ events: [] })); }
  return route.continue();
});

try {
  await page.goto(process.env.HOME_BASE_URL ?? 'http://localhost:3000/home');
  await expect(page.getByRole('heading', { name: 'Good to see you, Rahul' })).toBeVisible();
  await expect(page.getByRole('link', { name: /CEO sales report/ })).toBeVisible();
  await expect(page.getByText('Database reachable').first()).toBeVisible();
  if (await page.getByRole('region', { name: 'Ask Me product story' }).count()) throw new Error('Tour rendered before opening');
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 960 });
    for (const theme of ['light', 'dark', 'theme-ai']) {
      await page.evaluate(value => { document.documentElement.classList.remove('light', 'dark', 'theme-ai'); document.documentElement.classList.add(value); }, theme);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error(`Horizontal overflow: ${width}/${theme}`);
      if (theme === 'theme-ai' && width !== 820) await page.screenshot({ path: `tmp/home-workspace-ai-${width}.png`, fullPage: true });
    }
  }
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('navigation', { name: 'Sections' })).toBeVisible();
  await page.getByRole('button', { name: 'Close navigation' }).first().click();
  await expect(page.getByRole('navigation', { name: 'Sections' })).toBeHidden();
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole('button', { name: 'See how Ask Me works' }).click();
  await expect(page.getByRole('region', { name: 'Ask Me product story' })).toBeVisible();
  await page.getByRole('button', { name: 'Show Auto Report' }).click();
  await expect(page.getByRole('heading', { name: 'Turn one question into a report worth sharing.' })).toBeVisible();
  await page.getByRole('button', { name: 'Close product tour' }).click();
  await expect(page.getByRole('region', { name: 'Ask Me product story' })).toHaveCount(0);
  await page.getByRole('button', { name: 'View source details' }).click();
  await expect(page.getByRole('heading', { name: 'Connected Data Sources' })).toBeVisible();
  await page.getByRole('button', { name: 'Hide source details' }).click();
  await page.getByRole('button', { name: 'Revenue by month' }).click();
  await expect(page.getByRole('textbox', { name: 'Ask a question about your data' })).toHaveValue('Revenue by month');
  await page.getByRole('button', { name: 'Ask your data' }).click();
  await expect(page).toHaveURL(/\/chat\?q=Revenue%20by%20month/);
  await expect.poll(() => chatRequests).toBe(1);

  for (const scenario of ['empty', 'degraded', 'error']) {
    state = scenario;
    await page.goto('http://localhost:3000/home');
    await expect(page.getByRole('heading', { name: 'Good to see you, Rahul' })).toBeVisible();
    if (scenario === 'empty') await expect(page.getByText('No saved questions yet.')).toBeVisible();
    if (scenario === 'degraded') await expect(page.getByText('Database unreachable').first()).toBeVisible();
    if (scenario === 'error') await expect(page.getByText('Probe unavailable')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ask your data' })).toBeVisible();
  }
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ fixture: true, themes: 3, widths: [1440, 820, 390], states: ['populated', 'empty', 'degraded', 'error'], chatRequests, pageErrors: 0 }));
} finally { await browser.close(); }
