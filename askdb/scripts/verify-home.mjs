import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
await context.addCookies([{ name: 'nql_access', value: 'synthetic-home-fixture', domain: 'localhost', path: '/' }]);
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await page.route('**/*', async route => {
  const path = new URL(route.request().url()).pathname;
  if (path === '/auth/me' || path.endsWith('/auth/me')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'home-fixture', username: 'home', fullName: 'Home preview', email: 'home@example.com', role: 'admin', defaultIndustry: 'automotive', regionAccess: { unrestricted: true, zones: [], hideRegionFilter: false } }) });
  if (path === '/ready') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ dependencies: [{ name: 'Automotive warehouse', status: 'degraded', detail: 'Synthetic readiness fixture', latencyMs: null }] }) });
  if (path.endsWith('/industries')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ industries: [{ id: 'automotive', label: 'Automotive', isDefault: true, databaseAvailable: false, semanticPackLoaded: false }] }) });
  if (path.includes('/trust/')) return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
  return route.continue();
});
try {
  await page.goto(process.env.HOME_BASE_URL ?? 'http://localhost:3000/home');
  await expect(page.getByRole('heading', { name: 'Ask naturally. Understand precisely.' })).toBeVisible();
  await expect(page.getByText('Illustrative product walkthrough', { exact: false })).toBeVisible();
  await expect(page.getByText('Synthetic readiness fixture')).toBeVisible();
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ['light', 'dark', 'theme-ai']) {
      await page.evaluate(value => { document.documentElement.classList.remove('light', 'dark', 'theme-ai'); document.documentElement.classList.add(value); }, theme);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error(`Overflow at ${width}/${theme}`);
      if (width === 1440 && theme !== 'theme-ai') await page.screenshot({ path: `tmp/home-${theme}-scene-1.png` });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => { document.documentElement.classList.remove('light', 'dark'); document.documentElement.classList.add('theme-ai'); });
  for (const [index, label] of ['Trusted answer', 'Auto Report', 'Confident decision'].entries()) {
    await page.getByRole('button', { name: `Show ${label}` }).click();
    await page.screenshot({ path: `tmp/home-ai-scene-${index + 1}.png` });
  }
  await page.mouse.move(1400, 25);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Ask naturally. Understand precisely.' })).toBeVisible();
  await page.evaluate(() => { document.documentElement.classList.remove('light', 'dark'); document.documentElement.classList.add('theme-ai'); });
  for (const [index, label] of ['Trusted answer', 'Auto Report', 'Confident decision'].entries()) {
    if (index) await page.getByRole('button', { name: `Show ${label}` }).click();
    await page.screenshot({ path: `tmp/home-motion-${index + 1}-start.png` });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `tmp/home-motion-${index + 1}-middle.png` });
    await page.waitForTimeout(3400);
    await page.screenshot({ path: `tmp/home-motion-${index + 1}-settled.png` });
    const hidden = await page.locator('.home-motion-beat').evaluateAll(nodes => nodes.filter(node => Number(getComputedStyle(node).opacity) < 0.99).length);
    if (hidden) throw new Error(`${label} has ${hidden} hidden steps after settling`);
  }
  await page.getByRole('button', { name: 'Show Auto Report' }).click();
  await page.mouse.move(1430, 900);
  await page.locator('.home-story').hover();
  await expect(page.locator('.home-story')).toHaveAttribute('data-story-paused', 'true');
  const pausedState = await page.locator('.home-motion-beat').first().evaluate(node => getComputedStyle(node).animationPlayState);
  if (pausedState !== 'paused') throw new Error('Hover did not pause the scene sequence');
  await page.getByRole('button', { name: 'Next chapter' }).click();
  await expect(page.getByRole('heading', { name: 'See the change. Check the evidence. Decide.' })).toBeVisible();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.home-story')).toHaveAttribute('data-story-paused', 'true');
  const reducedHidden = await page.locator('.home-motion-beat').evaluateAll(nodes => nodes.filter(node => Number(getComputedStyle(node).opacity) < 0.99).length);
  if (reducedHidden) throw new Error('Reduced motion did not show the final state');
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ fixture: true, themes: 3, widths: [1440, 820, 390], scenes: 3, motionFrames: 'start/middle/settled', pageErrors: 0 }));
} finally { await browser.close(); }
