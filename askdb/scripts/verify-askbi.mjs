// Real Next components in Chrome with synthetic HTTP fixtures. No live DB/LLM.
import { chromium, expect } from '@playwright/test';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
await context.addCookies([{ name: 'nql_access', value: 'synthetic-fixture', domain: 'localhost', path: '/' }]);
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const usage = { llmCalls: 0, tokens: 0, usageComplete: true, elapsedMs: 2 };
const spec = { metrics: ['revenue'], dimensions: ['month'], filters: [], analysis: 'trend', viz: 'line', datePreset: 'custom', dateFrom: '2026-10-26', dateTo: '2026-11-01', limit: 500, orderDirection: 'asc', window: 3, rankMethod: 'rank' };
const panel = { id: 'p1', title: 'Daily revenue', kind: 'chart', spec, grain: 'day', daily: false, calculation: null, dateIntent: 'last week', section: 'Sales performance', rationale: 'Approved revenue calculation.' };
let report = { id: 'r1', revision: 1, title: 'Draft', saved: false, state: { plan: null, previous: null, turns: [], pending: null, usage } };
let runs = 0;
let enabled = true;
const points = [{ sales_day: '2026-10-26', revenue: 120000 }, { sales_day: '2026-10-27', revenue: 160000 }, { sales_day: '2026-10-28', revenue: 140000 }, { sales_day: '2026-10-29', revenue: 190000 }, { sales_day: '2026-10-30', revenue: 180000 }];
await page.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname;
  let body = {};
  if (path.endsWith('/auth/me')) body = { id: 'fixture-user', username: 'fixture', fullName: 'UI review', email: 'fixture@example.com', role: 'admin', defaultIndustry: 'automotive', regionAccess: { unrestricted: true, zones: ['West'], hideRegionFilter: false } };
  else if (path.endsWith('/semantic/pack')) body = { glossary: { terms: {} }, model: { measures: {}, tables: {} }, summary: { industry: 'automotive' } };
  else if (path.endsWith('/bi/capabilities')) body = { enabled, engine: 'askbi-v2', schemaVersion: 2, advancedEnabled: false, migration: '0014_bi_reports' };
  else if (path.endsWith('/bi/make-options')) body = { domain: 'make', label: 'Make', values: [{ value: 'Tata' }, { value: 'Mahindra' }] };
  else if (path.endsWith('/bi/region-options')) body = { domain: 'region', label: 'Region', values: [{ value: 'Mumbai' }] };
  else if (path.endsWith('/capabilities')) body = { metrics: [], dimensions: [], analyses: [], filterDomains: [], datePresets: [] };
  else if (path.endsWith('/inspect')) body = { valid: false, issues: [], analyses: [], metrics: [], dimensions: [], suggestions: [] };
  else if (path.endsWith('/bi/reports')) {
    if (route.request().method() === 'POST') {
      report = { id: route.request().postDataJSON().id, revision: 1, title: 'Draft', saved: false, state: { plan: null, previous: null, turns: [], pending: null, usage } };
      body = report;
    } else body = [];
  }
  else if (path.endsWith('/turns')) {
    const request = route.request().postDataJSON();
    report.revision++;
    if (request.question === 'Sales performance') {
      report.state.pending = { question: request.question, clarification: 'Which metric and period?', selectedPanelId: null };
      report.state.turns.push({ id: request.requestId, question: request.question, answer: 'Which metric and period?', kind: 'clarification', code: null, changedPanelIds: [] });
    } else if (request.question === 'Sales Report for CEO') {
      report.title = 'Sales Report for CEO';
      report.state.previous = structuredClone(report.state.plan);
      const definitions = [
        ['Revenue', 'revenue', null, 'kpi'], ['Units sold', 'units_sold', null, 'kpi'],
        ['Revenue trend', 'revenue', 'month', 'line'], ['Revenue by region', 'revenue', 'region', 'bar'],
        ['Units by make', 'units_sold', 'make', 'treemap'], ['Units by model', 'units_sold', 'model', 'bar'],
      ];
      report.state.plan = { version: 2, title: report.title, answerKind: 'report', assumptions: ['The period is the last completed month.'], reportFilter: { period: 'month', year: 2026, month: 10, make: null }, panels: definitions.map(([title, metric, dimension, viz], i) => ({ id: `leader-${i + 1}`, title, kind: dimension ? 'chart' : 'kpi', spec: { ...spec, metrics: [metric], dimensions: dimension ? [dimension] : [], viz, analysis: dimension === 'month' ? 'trend' : dimension ? 'top_n' : 'basic', dateFrom: '2026-10-01', dateTo: '2026-10-31' }, grain: dimension === 'month' ? 'week' : null, daily: false, calculation: null, dateIntent: 'last month', section: dimension ? dimension === 'month' ? 'Sales movement' : 'Performance breakdown' : 'Key metrics', rationale: 'Approved metric.' })) };
      report.state.pending = null;
      report.state.turns.push({ id: request.requestId, question: request.question, answer: 'Prepared Sales Report for CEO.', kind: 'answer', code: null, changedPanelIds: report.state.plan.panels.map(p => p.id) });
    } else {
      report.title = 'Weekly sales review';
      report.state.previous = structuredClone(report.state.plan);
      report.state.plan = { version: 2, title: report.title, answerKind: 'report', panels: [structuredClone(panel)], assumptions: [] };
      if (request.action === 'visualize') report.state.plan.panels[0].spec.viz = request.value;
      report.state.pending = null;
      if (request.action === 'save') report.saved = true;
      report.state.turns.push({ id: request.requestId, question: request.question || request.action, answer: request.action === 'visualize' ? 'Changed chart presentation.' : 'Prepared daily revenue for the requested dates.', kind: 'answer', code: null, changedPanelIds: ['p1'] });
    }
    body = report;
  } else if (path.endsWith('/run')) {
    runs++;
    const selected = report.state.plan?.panels.find(p => p.id === route.request().postDataJSON().panelId) ?? panel;
    const metric = selected.spec.metrics[0];
    const dimension = selected.spec.dimensions[0];
    const rows = !dimension ? [{ [metric]: metric === 'revenue' ? 1250000 : 42 }] : dimension === 'month' ? [{ month: 'Week 1', [metric]: 310000 }, { month: 'Week 2', [metric]: 390000 }, { month: 'Week 3', [metric]: 280000 }, { month: 'Week 4', [metric]: 270000 }] : ['North', 'South', 'West', 'East'].map((label, i) => ({ [dimension]: label, [metric]: metric === 'revenue' ? [420000, 350000, 280000, 200000][i] : [18, 12, 8, 4][i] }));
    const fixtureRows = selected.id === 'p1' ? points : rows;
    const x = selected.id === 'p1' ? 'sales_day' : dimension;
    body = { result: { title: selected.title, columns: dimension ? [x, metric] : [metric], rows: fixtureRows, sql: 'SELECT approved_metric', chart: dimension ? { x, y: metric, type: selected.spec.viz, series: [], points: fixtureRows } : null, recommendedViz: selected.spec.viz, insights: { executive: selected.id === 'p1' ? 'Highest returned revenue: INR 1,90,000 on 29 October.' : 'Synthetic UI fixture.', analyst: 'Synthetic UI fixture.' }, meta: { dataAsOf: '2026-11-01', metricFormat: metric === 'revenue' ? 'currency' : 'number', valueColumn: metric, warnings: [], notes: [] } }, evidence: 'fixture-evidence', elapsedMs: 10, queryCount: 3 };
  } else if (path.endsWith('/narration')) body = { paragraphs: ['For this selection: the strongest returned day is 29 October.'], aiUsed: false, usage };
  else if (path.endsWith('/analyses') || path.endsWith('/workspaces') || path.endsWith('/auto/boards')) body = [];
  else if (path.includes('/bi/reports/')) body = report;
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
try {
  const baseUrl = process.env.ASKBI_BASE_URL ?? 'http://localhost:3000';
  const redirect = await page.request.get(`${baseUrl}/outlook-redirect`);
  const csp = redirect.headers()['content-security-policy'] ?? '';
  if (!redirect.ok() || !csp.includes("frame-ancestors 'self'") || redirect.headers()['x-frame-options'] !== 'SAMEORIGIN') throw new Error(`Outlook redirect headers are incompatible with MSAL silent refresh: ${redirect.status()} ${csp}`);
  await page.goto(`${baseUrl}/analytics-builder`);
  await page.getByRole('button', { name: 'Auto Report · AskBI', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Start with a business question.' })).toBeVisible();
  const input = page.getByRole('textbox', { name: 'Ask a report question' });
  await input.fill('Sales performance');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Which metric and period?', { exact: true })).toBeVisible();
  if (runs !== 0) throw new Error('Clarification executed data');
  await input.fill('Revenue last week by day');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Daily revenue', exact: true })).toBeVisible();
  await expect(page.getByText('Highest returned revenue: INR 1,90,000 on 29 October.')).toBeVisible();
  await page.getByLabel('Daily revenue visualization').selectOption('bar');
  await expect(page.getByText('Changed chart presentation.', { exact: true })).toBeVisible();
  if (runs !== 1) throw new Error(`Presentation edit reran ${runs} queries`);
  await page.getByRole('button', { name: 'Custom Report', exact: true }).click();
  await page.getByRole('button', { name: 'Auto Report · AskBI', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Daily revenue', exact: true })).toBeVisible();
  for (const width of [1440, 820]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ['light', 'dark', 'theme-ai']) {
      await page.evaluate(theme => { document.documentElement.classList.remove('light', 'dark', 'theme-ai'); document.documentElement.classList.add(theme); }, theme);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error(`Overflow ${width}/${theme}`);
    }
    if (width === 1440) await page.screenshot({ path: 'askbi-desktop-verification.png', fullPage: true });
  }
  await page.getByRole('button', { name: 'AskBI', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.screenshot({ path: 'askbi-tablet-verification.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'New report', exact: true }).click();
  await page.getByRole('button', { name: /Sales Report for CEO/ }).click();
  await input.fill('Sales Report for CEO');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Units by model', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export PDF' })).toBeEnabled();
  await page.screenshot({ path: 'askbi-six-panel-verification.png', fullPage: true });
  await page.getByRole('heading', { name: 'Units by model', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'askbi-six-panel-bottom.png' });
  enabled = false;
  await page.reload();
  await page.getByRole('button', { name: 'Auto Report · AskBI', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'AskBI is not available on this API' })).toBeVisible();
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ fixtures: true, browser: 'Chrome', themes: 3, widths: [1440, 820], reducedMotion: true, dataQueries: runs, clarification: 'passed', modePreservation: 'passed', tabletDrawerKeyboard: 'passed', flagMismatch: 'passed', pageErrors: 0 }));
} catch (error) {
  console.error(JSON.stringify({ text: (await page.locator('body').innerText()).slice(0, 1600), errors }));
  throw error;
} finally { await browser.close(); }
