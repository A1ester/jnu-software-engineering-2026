// Run after browser-smoke.cjs against the same independent test database.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.BASE_URL || 'http://127.0.0.1:5002';
const artifacts = process.env.BROWSER_ARTIFACTS || 'test-results';
const checks = [];
const errors = [];
const check = name => { checks.push(name); console.log('OK ' + name); };
fs.mkdirSync(artifacts, { recursive: true });

async function open(browser, username, width = 1440, reducedMotion = 'no-preference') {
  const context = await browser.newContext({
    viewport: { width, height: width < 600 ? 844 : 1000 },
    deviceScaleFactor: 2, timezoneId: 'Asia/Shanghai', reducedMotion,
  });
  if (username) {
    const session = (await (await context.request.get(`${base}/api/session`)).json()).data;
    const result = await context.request.post(`${base}/api/login`, {
      headers: { 'X-CSRF-Token': session.csrf_token },
      data: { username, password: 'Demo12345!' },
    });
    assert.equal(result.status(), 200);
  }
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    const expectedLoginError = !username && message.location().url === `${base}/api/login` && message.text().includes('401');
    if (message.type() === 'error' && !expectedLoginError) errors.push(message.text());
  });
  await page.goto(base);
  await page.locator('.activity-card').first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  return page;
}

async function navigate(page, view, ready) {
  await page.goto(`${base}/#${view}`);
  await page.locator(ready).first().waitFor();
  await page.evaluate(() => document.fonts.ready);
}

async function noOverflow(page) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    `Horizontal overflow at ${page.viewportSize().width}px: ${page.url()}`);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
    args: ['--no-proxy-server'],
  });
  try {
    const student = await open(browser, 'student');
    const style = await student.evaluate(() => {
      const body = getComputedStyle(document.body);
      const card = getComputedStyle(document.querySelector('.activity-card'));
      const number = getComputedStyle(document.querySelector('.hero-number'));
      return {
        paper: body.backgroundColor, grid: body.backgroundImage,
        border: parseFloat(card.borderTopWidth), declaredBorder: getComputedStyle(document.documentElement).getPropertyValue('--border').trim(),
        ink: card.borderTopColor, radius: card.borderRadius,
        shadow: card.boxShadow, numberSize: parseFloat(number.fontSize), digits: number.fontVariantNumeric,
        fonts: Array.from(document.fonts, font => ({ family: font.family, status: font.status })),
        count: Number(document.querySelector('.hero-number').textContent),
        cards: document.querySelectorAll('.activity-card').length,
      };
    });
    assert.equal(style.paper, 'rgb(251, 243, 228)');
    assert.ok(style.grid.includes('rgb(234, 223, 203)'));
    assert.equal(style.declaredBorder, '2.5px solid #111111');
    // Chromium may snap fractional borders down to a physical-pixel boundary.
    assert.ok(style.border >= 2 && style.border <= 2.5);
    assert.equal(style.ink, 'rgb(17, 17, 17)');
    assert.equal(style.radius, '12px');
    assert.equal(style.shadow, 'rgb(17, 17, 17) 6px 6px 0px 0px');
    assert.ok(style.numberSize >= 120);
    assert.equal(style.digits, 'tabular-nums');
    assert.equal(style.count, style.cards);
    assert.equal(style.fonts.length, 2);
    assert.ok(style.fonts.every(font => font.status === 'loaded'));
    check('Paper, grid, borders, hard shadow, local fonts and actual activity count');
    await student.screenshot({ path: `${artifacts}/neo-desktop.png`, fullPage: true, scale: 'css' });

    const control = student.locator('.nav-link[href="#clubs"]');
    await control.hover();
    await student.waitForTimeout(240);
    const hover = await control.evaluate(node => ({ transform: getComputedStyle(node).transform, shadow: getComputedStyle(node).boxShadow }));
    assert.equal(hover.transform, 'matrix(1, 0, 0, 1, -2, -2)');
    assert.equal(hover.shadow, 'rgb(17, 17, 17) 8px 8px 0px 0px');
    await student.mouse.down();
    await student.waitForTimeout(180);
    const press = await control.evaluate(node => ({ transform: getComputedStyle(node).transform, shadow: getComputedStyle(node).boxShadow }));
    assert.equal(press.transform, 'matrix(1, 0, 0, 1, 6, 6)');
    assert.equal(press.shadow, 'rgb(17, 17, 17) 0px 0px 0px 0px');
    await student.mouse.up();
    await student.locator('.club-card').first().waitFor();
    check('Hover lift and physical press');

    const visitor = await open(browser);
    await visitor.getByRole('button', { name: '登录 / 体验', exact: true }).click();
    await visitor.locator('input[name="password"]').fill('IncorrectDemoPassword');
    await visitor.getByRole('button', { name: '进入校园空间', exact: true }).click();
    await visitor.locator('.error-box').waitFor();
    await visitor.waitForFunction(() => document.body.dataset.statusAccent === 'red');
    assert.equal(await visitor.locator('.error-box').evaluate(node => getComputedStyle(node).backgroundColor), 'rgb(229, 50, 45)');
    assert.ok((await visitor.locator('.status-badge.green').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).backgroundColor))).every(color => color === 'rgb(251, 243, 228)'));
    await visitor.getByRole('button', { name: '关闭窗口', exact: true }).click();
    await visitor.waitForFunction(() => document.body.dataset.statusAccent === 'green');
    check('Mixed statuses retain labels and only one red or green accent');

    const staff = await open(browser, 'staff');
    await navigate(staff, 'statistics', '.chart-series');
    const rows = await staff.locator('table tbody tr').evaluateAll(nodes => nodes.map(node => Array.from(node.querySelectorAll('td')).slice(2).map(cell => Number(cell.textContent))));
    const chart = await staff.locator('.chart-row').evaluateAll(nodes => nodes.map(node => Array.from(node.querySelectorAll('.chart-series')).map(series => {
      const bar = series.querySelector('.chart-bar');
      return { value: Number(series.querySelector('.chart-value').textContent), width: bar.getBoundingClientRect().width, percentage: parseFloat(bar.style.getPropertyValue('--bar-size')) };
    })));
    assert.deepEqual(chart.map(group => group.map(series => series.value)), rows);
    const maximum = Math.max(1, ...rows.flat());
    chart.flat().forEach(series => {
      assert.ok(Math.abs(series.percentage - series.value / maximum * 100) < .001);
      assert.ok(series.value ? series.width > 0 : series.width === 0);
    });
    assert.ok((await staff.locator('.stat-card strong').evaluateAll(nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize)))).every(size => size >= 120));
    assert.ok(await staff.locator('.chart-bar.secondary').first().evaluate(node => getComputedStyle(node).backgroundImage.startsWith('radial-gradient')));
    await staff.screenshot({ path: `${artifacts}/neo-statistics.png`, fullPage: true, scale: 'css' });
    check('Chart counts and bar proportions match table; halftone and large statistics');

    await staff.getByRole('combobox', { name: '统计社团', exact: true }).selectOption('2');
    await staff.getByText('暂无活动统计', { exact: true }).waitFor();
    assert.equal(await staff.locator('.statistics-chart').count(), 0);
    assert.deepEqual(await staff.locator('.stat-card strong').allTextContents(), ['0', '0', '0', '0']);
    check('Empty club statistics show zero counts without fabricated bars');

    const mobile = await open(browser, 'staff', 390);
    for (const [view, ready] of [['activities', '.activity-card'], ['clubs', '.club-card'], ['dashboard', '.stat-card'], ['statistics', '.chart-series'], ['calendar', '.calendar-grid'], ['resources', '.venue-grid'], ['audit', '.panel']]) {
      await navigate(mobile, view, ready);
      await noOverflow(mobile);
      if (view === 'statistics') {
        assert.ok(await mobile.locator('.statistics-toolbar select').evaluate(node => node.getBoundingClientRect().width >= 200), 'Club selector label is squeezed');
        await mobile.screenshot({ path: `${artifacts}/neo-mobile-statistics.png`, fullPage: true, scale: 'css' });
      }
    }
    await navigate(mobile, 'activities', '.activity-card');
    await mobile.screenshot({ path: `${artifacts}/neo-mobile.png`, fullPage: true, scale: 'css' });
    await mobile.locator('.activity-card').first().getByRole('button').click();
    const dialog = await mobile.locator('dialog').evaluate(node => ({ width: node.getBoundingClientRect().width, content: node.scrollWidth, client: node.clientWidth }));
    assert.ok(dialog.width <= 390 && dialog.content <= dialog.client + 1);
    check('390px layouts and dialog contents without horizontal overflow');

    const narrow = await open(browser, 'student', 320);
    await noOverflow(narrow);
    await navigate(narrow, 'calendar', '.calendar-grid');
    await noOverflow(narrow);
    check('320px activity and calendar layouts');

    const reduced = await open(browser, 'student', 1440, 'reduce');
    assert.equal(await reduced.locator('.nav-link').first().evaluate(node => getComputedStyle(node).transitionDuration), '0s');
    check('Reduced motion preference');
    assert.deepEqual(errors, [], 'Browser or console errors');
    console.log(JSON.stringify({ passed: checks.length, checks, browserErrors: errors }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
