// Browser verification with synthetic API fixtures; never a live warehouse test.
import { chromium } from '@playwright/test';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
await context.addCookies([{ name: 'nql_access', value: 'synthetic-ui-fixture', domain: 'localhost', path: '/' }]);
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let runCount = 0;
const spec = { metrics: ['revenue'], dimensions: ['month'], filters: [], analysis: 'trend', viz: 'line', limit: 500, datePreset: 'custom', dateFrom: '2026-10-26', dateTo: '2026-11-01', orderDirection: 'asc', window: 3, rankMethod: 'rank' };
const panel = { id: 'p1', title: 'Daily revenue', kind: 'chart', spec, daily: true, rationale: 'Governed automotive revenue by day.' };
const plan = { answerKind: 'analysis', title: 'Daily sales last week', panels: [panel], assumptions: [], clarification: null };
const result = { title: 'Daily revenue', columns: ['sales_day', 'revenue'], rows: [{ sales_day: '2026-10-26', revenue: 120 }, { sales_day: '2026-10-27', revenue: 180 }], sql: 'SELECT governed_revenue', chart: { x: 'sales_day', y: 'revenue', type: 'line', series: [], points: [{ sales_day: '2026-10-26', revenue: 120 }, { sales_day: '2026-10-27', revenue: 180 }] }, recommendedViz: 'line', insights: { executive: 'Revenue rose across the two returned days.', analyst: 'Computed from governed sales.' }, meta: { dataAsOf: '2026-11-01', metricFormat: 'currency', notes: [], warnings: [] } };
await page.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname;
  let body = {};
  if (path.endsWith('/auth/me')) body = { id: 'ui-user', username: 'ui-test', fullName: 'UI Test', email: 'ui@example.com', role: 'admin', defaultIndustry: 'automotive', regionAccess: { unrestricted: true, zones: ['West'], hideRegionFilter: false } };
  else if (path.endsWith('/semantic/pack')) body = { glossary: { terms: {} }, summary: { industry: 'automotive' } };
  else if (path.endsWith('/capabilities')) body = { metrics: [], dimensions: [], analyses: [], datePresets: [] };
  else if (path.endsWith('/workspace/plan')) {
    const request = route.request().postDataJSON();
    body = { plan: structuredClone(plan), elapsedMs: 4, llmCalls: 0, tokens: 0 };
    if (request.previous) body.plan.panels[0].spec.viz = 'bar';
  }
  else if (path.endsWith('/workspace/run')) { runCount++; body = { result, evidence: 'synthetic-evidence', elapsedMs: 8, queryCount: 3 }; }
  else if (path.endsWith('/workspace/narration')) body = { paragraphs: ['Revenue rose across the two returned days.'], aiUsed: false };
  else if (path.endsWith('/workspaces') || path.endsWith('/analyses') || path.endsWith('/auto/boards')) body = [];
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
try {
  await page.goto('http://localhost:3003/analytics-builder');
  const input = page.getByRole('textbox', { name: /^Ask Analytics/ });
  await input.fill('Daily sales last week');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('heading', { name: 'Daily revenue' }).waitFor();
  await page.getByText('Revenue rose across the two returned days.').first().waitFor();
  await page.getByRole('button', { name: 'Refine', exact: true }).click();
  await input.fill('Change this chart to a bar chart');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByLabel('Daily revenue visualization').selectOption('area');
  if (runCount !== 1) throw new Error(`Presentation edit reran data: ${runCount}`);
  for (const width of [1440, 820]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ['light', 'dark', 'theme-ai']) {
      await page.evaluate(theme => { document.documentElement.classList.remove('light', 'dark', 'theme-ai'); document.documentElement.classList.add(theme); }, theme);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      if (overflow) throw new Error(`Horizontal overflow at ${width}/${theme}`);
    }
  }
  await page.screenshot({ path: 'analytics-workspace-verification.png', fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ browser: 'Chrome', fixtures: true, themes: 3, widths: [1440, 820], reducedMotion: true, queryRuns: runCount, pageErrors: errors.length }));
} catch (error) {
  console.error(JSON.stringify({ url: page.url(), text: (await page.locator('body').innerText()).slice(0, 1800), errors }));
  await page.screenshot({ path: 'analytics-workspace-verification.png', fullPage: true });
  throw error;
} finally { await browser.close(); }
