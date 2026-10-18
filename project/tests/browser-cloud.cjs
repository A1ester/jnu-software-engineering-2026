// Requires a private access.json generated for an independent cloud test deployment.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
if (!process.env.CLOUD_TEST_ACCESS_FILE) throw new Error('Set CLOUD_TEST_ACCESS_FILE to the private access file.');
const access = JSON.parse(fs.readFileSync(process.env.CLOUD_TEST_ACCESS_FILE, 'utf8'));
const base = access.url.replace(/\/$/, '');
const checks = [];
const pageErrors = [];
function check(name) { checks.push(name); console.log('OK ' + name); }

async function main() {
  const browser = await chromium.launch({
    headless: true, args: ['--no-proxy-server'],
    ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
  });
  const contexts = [];
  try {
    const anonymous = await browser.newContext();
    const denied = await anonymous.request.get(base);
    assert.equal(denied.status(), 401);
    check('External HTTPS requires test-site credentials');
    await anonymous.close();

    async function login(username, password = 'Demo12345!') {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        timezoneId: 'Asia/Shanghai',
        httpCredentials: { username: access.gate_username, password: access.gate_password, send: 'always' },
      });
      contexts.push(context);
      let response = await context.request.get(`${base}/api/session`);
      assert.equal(response.status(), 200);
      const token = (await response.json()).data.csrf_token;
      response = await context.request.post(`${base}/api/login`, {
        headers: { 'X-CSRF-Token': token }, data: { username, password },
      });
      assert.equal(response.status(), 200);
      const session = (await response.json()).data;
      const page = await context.newPage();
      page.on('pageerror', error => pageErrors.push(error.message));
      await page.goto(base);
      await page.locator('.activity-card').first().waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.getByRole('button', { name: '退出', exact: true }).waitFor();
      assert.ok((await context.cookies()).some(cookie => cookie.name === 'campus_session' && cookie.secure && cookie.httpOnly));
      return { context, page, csrf: session.csrf_token, user: session.user };
    }

    const student = await login('student');
    const leader = await login('leader');
    const staff = await login('staff');
    const president = await login(access.leader_username, access.leader_password);
    assert.equal(staff.user.role, 'staff');
    assert.equal(president.user.role, 'student');
    const ownClub = president.user.memberships.find(membership => membership.role === 'leader');
    assert.ok(ownClub && ownClub.club_name.includes('智能基座'));
    assert.equal((await president.context.request.get(`${base}/api/clubs/1/members`)).status(), 403);
    check('Four account contexts, HTTPS cookies and president ownership');

    await president.page.goto(`${base}/#clubs`);
    const club = president.page.locator('.club-card').filter({ hasText: ownClub.club_name });
    await club.waitFor();
    assert.ok((await club.textContent()).includes('番禺校区'));
    await club.getByRole('button', { name: '了解社团 ↗', exact: true }).click();
    await president.page.locator('dialog').getByText(ownClub.club_name, { exact: true }).waitFor();
    assert.ok((await president.page.locator('dialog').textContent()).includes(access.leader_username));
    check('Confirmed club profile appears through the external URL');

    async function post(actor, path, data, status = 200) {
      const response = await actor.context.request.post(`${base}${path}`, {
        headers: { 'X-CSRF-Token': actor.csrf }, data,
      });
      assert.equal(response.status(), status, path);
      return (await response.json()).data;
    }
    const now = Date.now();
    const activity = await post(leader, '/api/activities', {
      club_id: 1, title: '云端联调演示活动', theme: '部署验证',
      description: '仅用于云端部署流程验证，不代表真实社团活动。', location: '线上测试环境', capacity: 5,
      registration_deadline: new Date(now + 3600000).toISOString(),
      start_time: new Date(now + 7200000).toISOString(), end_time: new Date(now + 10800000).toISOString(),
      waitlist_enabled: true,
    }, 201);
    await post(leader, `/api/activities/${activity.id}/transition`, { action: 'submit' });
    await post(staff, `/api/activities/${activity.id}/transition`, { action: 'approve' });
    await post(leader, `/api/activities/${activity.id}/transition`, { action: 'publish' });
    await post(leader, `/api/activities/${activity.id}/transition`, { action: 'open_registration' });
    const registration = await post(student, `/api/activities/${activity.id}/registrations`, {}, 201);
    assert.equal(registration.status, 'confirmed');
    await post(student, `/api/registrations/${registration.id}/cancel`, {});
    await post(leader, `/api/activities/${activity.id}/transition`, { action: 'cancel', reason: '云端部署验证完成，关闭演示报名。' });
    check('External create, review, publish, register and cancellation flow');

    await president.page.locator('dialog .dialog-close').click();
    await president.page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await president.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await president.page.screenshot({ path: 'test-results/cloud-mobile.png', fullPage: true });
    await leader.page.goto(`${base}/#dashboard`);
    await leader.page.locator('.stat-card').first().waitFor();
    await leader.page.screenshot({ path: 'test-results/cloud-desktop.png', fullPage: true });
    assert.deepEqual(pageErrors, []);
    check('Mobile layout and rendered pages without uncaught errors');
    console.log(JSON.stringify({ passed: checks.length, checks, pageErrors }, null, 2));
  } finally {
    await Promise.allSettled(contexts.map(context => context.close()));
    await browser.close();
  }
}

main().catch(error => {
  let message = error.message;
  for (const secret of [access.gate_password, access.leader_password,
    Buffer.from(`${access.gate_username}:${access.gate_password}`).toString('base64')]) {
    message = message.replaceAll(secret, '[redacted]');
  }
  console.error(message);
  process.exitCode = 1;
});
