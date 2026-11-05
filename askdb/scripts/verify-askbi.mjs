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
  else if (path.endsWith('/capabilities')) body = { metrics: [], dimensions: [], analyses: [], filterDomains: [], datePresets: [] };
  else if (path.endsWith('/inspect')) body = { valid: false, issues: [], analyses: [], metrics: [], dimensions: [], suggestions: [] };
  else if (path.endsWith('/bi/reports')) body = route.request().method() === 'POST' ? report : [];
  else if (path.endsWith('/turns')) {
    const request = route.request().postDataJSON();
    report.revision++;
    if (request.question === 'Sales performance') {
      report.state.pending = { question: request.question, clarification: 'Which metric and period?', selectedPanelId: null };
      report.state.turns.push({ id: request.requestId, question: request.question, answer: 'Which metric and period?', kind: 'clarification', code: null, changedPanelIds: [] });
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
    body = { result: { title: panel.title, columns: ['sales_day', 'revenue'], rows: points, sql: 'SELECT approved_revenue', chart: { x: 'sales_day', y: 'revenue', type: 'line', series: [], points }, recommendedViz: 'line', insights: { executive: 'Highest returned revenue: INR 1,90,000 on 29 October.', analyst: 'Synthetic UI fixture.' }, meta: { dataAsOf: '2026-11-01', metricFormat: 'currency', valueColumn: 'revenue', warnings: [], notes: [] } }, evidence: 'fixture-evidence', elapsedMs: 10, queryCount: 3 };
  } else if (path.endsWith('/narration')) body = { paragraphs: ['For this selection: the strongest returned day is 29 October.'], aiUsed: false, usage };
  else if (path.endsWith('/analyses') || path.endsWith('/workspaces') || path.endsWith('/auto/boards')) body = [];
  else if (path.includes('/bi/reports/')) body = report;
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
try {
  await page.goto(`${process.env.ASKBI_BASE_URL ?? 'http://localhost:3000'}/analytics-builder`);
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
