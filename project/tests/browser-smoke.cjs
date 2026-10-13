// Run against a fresh, independently seeded test database, never a working database.
// BASE_URL selects the test service. Playwright is an optional browser-test dependency.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.BASE_URL || 'http://127.0.0.1:5002';
const checks = [];
checks.push = function (...items) {
  items.forEach(item => console.log('OK ' + item));
  return Array.prototype.push.apply(this, items);
};
const errors = [];
const artifactDir = process.env.BROWSER_ARTIFACTS || 'test-results';
const unique = Date.now().toString().slice(-8);
const activityTitle = `摄影分享会 ${unique}`;
const clubName = `校园天文社 ${unique}`;
const injection = '<img src=x onerror="window.__uiXss=1">';
fs.mkdirSync(artifactDir, { recursive: true });

async function login(browser, username, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, timezoneId: 'Asia/Shanghai' });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base);
  await page.locator('.activity-card').first().waitFor();
  await page.getByRole('button', { name: '登录 / 体验', exact: true }).click();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill('Demo12345!');
  await page.getByRole('button', { name: '进入校园空间', exact: true }).click();
  await page.getByRole('button', { name: '退出', exact: true }).waitFor();
  return page;
}

async function navigate(page, hash, heading) {
  await page.locator('dialog').evaluateAll(nodes => nodes.forEach(node => node.close()));
  // A new document also refreshes changes made by the other role's browser.
  await page.goto(`${base}/?validation=${Date.now()}#${hash}`);
  await page.locator('main').getByText(heading, { exact: true }).first().waitFor();
}

function response(page, suffix, method) {
  return page.waitForResponse(r => new URL(r.url()).pathname.endsWith(suffix) && r.request().method() === method);
}

async function submit(page, suffix, name, expected = 200) {
  const arrived = response(page, suffix, 'POST');
  await page.locator('dialog').getByRole('button', { name, exact: true }).click();
  assert.equal((await arrived).status(), expected);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
    args: ['--no-proxy-server'],
  });
  try {
    const student = await login(browser, 'student');
    checks.push('UI login and session');
    await student.screenshot({ path: `${artifactDir}/desktop.png`, fullPage: true });

    await navigate(student, 'clubs', '从兴趣开始，找到归属');
    await student.locator('.club-card').filter({ hasText: '校园摄影社' }).getByRole('button').click();
    await student.getByRole('button', { name: '申请加入社团', exact: true }).click();
    await student.locator('textarea[name="message"]').fill('喜欢校园摄影，希望参与社团实践。');
    await submit(student, '/clubs/1/applications', '提交申请', 201);
    await student.locator('dialog').waitFor({ state: 'hidden' });
    checks.push('UI club application');

    const leader = await login(browser, 'leader');
    await navigate(leader, 'dashboard', '我的工作台');
    await leader.getByRole('button', { name: '成员与申请', exact: true }).click();
    const applicationRow = leader.locator('dialog .list-row').filter({ hasText: '演示学生' }).filter({ hasText: '希望加入社团' });
    const approved = response(leader, '/review', 'POST');
    await applicationRow.getByRole('button', { name: '通过', exact: true }).click();
    assert.equal((await approved).status(), 200);
    await leader.locator('dialog').getByText('有效成员', { exact: false }).first().waitFor();
    checks.push('UI leader membership approval');

    await navigate(student, 'activities', '值得参与的校园活动');
    await student.locator('.activity-card').filter({ hasText: '校园摄影漫步' }).getByRole('button').click();
    await submit(student, '/activities/1/registrations', '报名参加', 201);
    await student.locator('dialog').getByRole('button', { name: '取消报名', exact: true }).waitFor();
    checks.push('UI registration confirmation');
    const cancelled = response(student, '/cancel', 'POST');
    await student.getByRole('button', { name: '取消报名', exact: true }).click();
    assert.equal((await cancelled).status(), 200);
    await student.getByRole('button', { name: '报名参加', exact: true }).waitFor();
    checks.push('UI personal cancellation');

    await navigate(leader, 'dashboard', '我的工作台');
    await leader.getByRole('button', { name: '＋ 创建活动', exact: true }).click();
    await leader.locator('[name="club_id"]').selectOption('1');
    await leader.locator('[name="title"]').fill(activityTitle);
    await leader.locator('[name="theme"]').fill('摄影');
    await leader.locator('dialog [name="description"]').fill(`校园摄影经验分享。安全显示测试：${injection}`);
    await leader.locator('[name="location"]').fill('学生交流中心');
    await leader.locator('[name="capacity"]').fill('8');
    const localTime = days => {
      const dt = new Date(Date.now() + days * 86400000);
      return new Date(dt.getTime() + 8 * 3600000).toISOString().slice(0, 16);
    };
    await leader.locator('[name="registration_deadline"]').fill(localTime(2));
    await leader.locator('[name="start_time"]').fill(localTime(3));
    await leader.locator('[name="end_time"]').fill(localTime(4));
    await submit(leader, '/api/activities', '保存草稿', 201);
    await leader.locator('dialog').waitFor({ state: 'hidden' });
    const draft = leader.locator('main .list-row').filter({ hasText: activityTitle });
    await draft.getByRole('button', { name: '详情', exact: true }).click();
    await leader.locator('dialog').getByText(`校园摄影经验分享。安全显示测试：${injection}`, { exact: true }).waitFor();
    assert.equal(await leader.locator('dialog img').count(), 0);
    assert.equal(await leader.evaluate(() => window.__uiXss), undefined);
    checks.push('UI draft creation and safe text rendering');
    await leader.getByRole('button', { name: '关闭窗口', exact: true }).click();
    const submitted = response(leader, '/transition', 'POST');
    await draft.getByRole('button', { name: '提交审核', exact: true }).click();
    assert.equal((await submitted).status(), 200);
    checks.push('UI activity submission');

    const staff = await login(browser, 'staff');
    await navigate(staff, 'dashboard', '社团管理中心');
    const reviewRow = staff.locator('main .list-row').filter({ hasText: activityTitle });
    const reviewed = response(staff, '/transition', 'POST');
    await reviewRow.getByRole('button', { name: '审核通过', exact: true }).click();
    assert.equal((await reviewed).status(), 200);
    checks.push('UI management-center review');

    await navigate(leader, 'dashboard', '我的工作台');
    const approvedRow = leader.locator('main .list-row').filter({ hasText: activityTitle });
    const published = response(leader, '/transition', 'POST');
    await approvedRow.getByRole('button', { name: '发布活动', exact: true }).click();
    assert.equal((await published).status(), 200);
    await approvedRow.getByRole('button', { name: '开放报名', exact: true }).waitFor();
    const opened = response(leader, '/transition', 'POST');
    await approvedRow.getByRole('button', { name: '开放报名', exact: true }).click();
    assert.equal((await opened).status(), 200);
    checks.push('UI publish and separately open registration');

    await navigate(leader, 'activities', '值得参与的校园活动');
    const searchResponse = leader.waitForResponse(r => r.url().includes('/api/activities?') && r.request().method() === 'GET');
    await leader.getByRole('searchbox', { name: '搜索活动' }).fill(activityTitle);
    await leader.getByRole('button', { name: '筛选', exact: true }).click();
    assert.equal((await searchResponse).status(), 200);
    await leader.locator('.activity-card').filter({ hasText: activityTitle }).waitFor();
    assert.equal(await leader.locator('.activity-card').count(), 1);
    checks.push('UI activity filtering');

    const member = await login(browser, 'member');
    await navigate(member, 'tasks', '一起筹备，让活动更好');
    const taskSelect = member.getByRole('combobox', { name: '准备摄影路线的任务状态', exact: true });
    const taskUpdated = response(member, '/tasks/1', 'PATCH');
    await taskSelect.selectOption('in_progress');
    assert.equal((await taskUpdated).status(), 200);
    await member.locator('.task-column[aria-label="进行中"]').getByText('准备摄影路线', { exact: true }).waitFor();
    checks.push('UI task progress');
    await navigate(member, 'activities', '值得参与的校园活动');
    await member.locator('.activity-card').filter({ hasText: '摄影交流实践' }).getByRole('button').click();
    await member.getByRole('button', { name: '现场签到登记', exact: true }).click();
    await submit(member, '/activities/2/check-ins', '确认到场');
    await member.locator('dialog').getByText('已签到', { exact: true }).waitFor();
    checks.push('UI authorized check-in');

    await navigate(student, 'clubs', '从兴趣开始，找到归属');
    await student.getByRole('button', { name: '＋ 申请成立社团', exact: true }).click();
    await student.locator('[name="name"]').fill(clubName);
    await student.locator('dialog [name="description"]').fill('校园天文观测与知识交流。');
    await submit(student, '/api/club-registrations', '提交备案申请', 201);
    await student.locator('dialog').waitFor({ state: 'hidden' });
    await navigate(staff, 'dashboard', '社团管理中心');
    const filingReview = response(staff, '/review', 'POST');
    await staff.locator('main .list-row').filter({ hasText: clubName }).getByRole('button', { name: '审核通过', exact: true }).click();
    assert.equal((await filingReview).status(), 200);
    await navigate(student, 'dashboard', '我的工作台');
    await student.locator('main .list-row').filter({ hasText: clubName }).getByRole('button', { name: '成员与申请', exact: true }).waitFor();
    checks.push('UI applicant becomes leader only after approval');

    await navigate(student, 'notifications', '校园里的消息，及时收到');
    const noticeRead = response(student, '/read', 'POST');
    await student.getByRole('button', { name: '标为已读', exact: true }).first().click();
    assert.equal((await noticeRead).status(), 200);
    checks.push('UI notification read');

    await navigate(staff, 'audit', '管理记录');
    await staff.locator('table tbody tr').first().waitFor();
    assert.equal(await staff.locator('main').getByText('activity_submit', { exact: true }).count(), 0);
    await staff.screenshot({ path: `${artifactDir}/staff.png`, fullPage: true });
    checks.push('UI translated audit');

    await navigate(student, 'calendar', '把期待，写进日历');
    assert.ok(await student.locator('.calendar-day').count() >= 28);
    await student.locator('.calendar-day').filter({ has: student.locator('.calendar-event-count') }).first().click();
    await student.locator('.activity-card').first().waitFor();
    checks.push('UI local-day activity calendar');

    await navigate(student, 'recommendations', '从兴趣出发，遇见新活动');
    await student.locator('input[name="themes"][value="摄影"]').check();
    const recommended = student.waitForResponse(r => r.url().includes('/api/recommendations?'));
    await student.getByRole('button', { name: '更新兴趣推荐', exact: true }).click();
    assert.equal((await recommended).status(), 200);
    await student.locator('main').getByText(/匹配偏好主题/).first().waitFor();
    checks.push('UI explainable interest recommendation');

    await navigate(member, 'todos', '把下一件事，安排清楚');
    await member.locator('main .list-row').filter({ hasText: '准备摄影路线' }).getByRole('button', { name: '前往处理' }).waitFor();
    assert.ok((await member.locator('main').innerText()).includes('截止：'));
    checks.push('UI actionable personal todos');

    await navigate(leader, 'resources', '社团活动资源');
    await leader.getByRole('button', { name: '＋ 申请活动场地', exact: true }).click();
    await leader.locator('dialog [name="activity_id"]').selectOption('3');
    await leader.locator('dialog [name="venue_id"]').selectOption('1');
    await submit(leader, '/activities/3/venue-applications', '提交场地申请', 201);
    await leader.locator('dialog').waitFor({ state: 'hidden' });
    await navigate(staff, 'resources', '场地资源与审批');
    const reserved = response(staff, '/review', 'POST');
    await staff.locator('main .list-row').filter({ hasText: '秋日主题展筹备' }).getByRole('button', { name: '批准场地申请', exact: true }).click();
    assert.equal((await reserved).status(), 200);
    checks.push('UI venue application and staff approval');

    await navigate(leader, 'activities', '值得参与的校园活动');
    await leader.locator('.activity-card').filter({ hasText: activityTitle }).getByRole('button').click();
    await leader.getByRole('button', { name: '活动物资', exact: true }).click();
    await leader.locator('dialog [name="name"]').fill('签到笔');
    await leader.locator('dialog [name="quantity"]').fill('5');
    await submit(leader, '/materials', '添加物资', 201);
    await leader.locator('dialog').waitFor({ state: 'hidden' });
    await leader.locator('.activity-card').filter({ hasText: activityTitle }).getByRole('button').click();
    await leader.getByRole('button', { name: '活动物资', exact: true }).click();
    const prepared = response(leader, '/materials/1', 'PATCH');
    await leader.getByRole('combobox', { name: '签到笔的物资状态', exact: true }).selectOption('ready');
    assert.equal((await prepared).status(), 200);
    checks.push('UI material request and preparation');

    await navigate(member, 'activities', '值得参与的校园活动');
    await member.locator('.activity-card').filter({ hasText: '摄影复盘分享' }).getByRole('button').click();
    await member.getByRole('button', { name: '评价本次活动', exact: true }).click();
    await member.locator('dialog [name="rating"]').selectOption('5');
    await member.locator('dialog [name="comment"]').fill('活动安排清楚，摄影交流很有帮助。');
    await submit(member, '/activities/4/feedback', '提交活动评价', 201);
    await member.locator('dialog').waitFor({ state: 'hidden' });
    await navigate(leader, 'statistics', '看见每一次参与');
    await leader.locator('table tbody tr').filter({ hasText: '摄影复盘分享' }).waitFor();
    const csvDownload = leader.waitForEvent('download');
    await leader.getByRole('link', { name: '下载统计 CSV', exact: true }).click();
    assert.ok((await csvDownload).suggestedFilename().endsWith('.csv'));
    checks.push('UI finished-activity feedback and statistics export');

    await navigate(student, 'activities', '值得参与的校园活动');
    await student.locator('.activity-card').filter({ hasText: '校园摄影漫步' }).getByRole('button').click();
    await student.getByRole('button', { name: '举报活动', exact: true }).click();
    await student.locator('dialog [name="reason"]').fill('请核对现场组织说明。');
    await submit(student, '/activities/1/reports', '提交举报', 201);
    await student.locator('dialog').waitFor({ state: 'hidden' });
    await navigate(staff, 'reports', '活动举报处理');
    await staff.locator('main .list-row').filter({ hasText: '请核对现场组织说明。' }).getByRole('button', { name: '记录处理结果', exact: true }).click();
    await staff.locator('dialog [name="resolution"]').fill('已联系活动负责人补充说明。');
    await submit(staff, '/reports/1/resolve', '确认处理完成');
    await staff.locator('dialog').waitFor({ state: 'hidden' });
    await staff.locator('main').getByText(/已联系活动负责人补充说明/).waitFor();
    checks.push('UI private report and management resolution');

    const mobile = await login(browser, 'student', { width: 390, height: 844 });
    await mobile.screenshot({ path: `${artifactDir}/mobile.png`, fullPage: true });
    assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile horizontal overflow');
    await mobile.locator('.activity-card').first().getByRole('button').click();
    assert.ok(await mobile.locator('dialog').evaluate(node => node.getBoundingClientRect().width <= innerWidth), 'Mobile dialog exceeds viewport');
    await navigate(mobile, 'calendar', '把期待，写进日历');
    assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile calendar horizontal overflow');
    checks.push('UI mobile layout and dialog');
    assert.deepEqual(errors, [], 'Uncaught browser errors');
    console.log(JSON.stringify({ passed: checks.length, checks, browserErrors: errors }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
