'use strict';

(() => {
  const state = {
    user: null, csrf: '', view: 'activities', generation: 0, unread: 0,
    filters: { q: '', theme: '', club_id: '', date: '' }, themes: [], recordTab: 'registrations',
    calendarMonth: new Date(new Date().getFullYear(), new Date().getMonth(), 1), calendarDay: '',
    preferredThemes: [], statisticsClub: '',
  };
  const main = document.getElementById('main');
  const labels = { activities: '活动广场', clubs: '社团发现', calendar: '活动日历', recommendations: '兴趣推荐', dashboard: '我的工作台', todos: '待办事项', records: '我的参与', tasks: '筹备任务', resources: '活动资源', statistics: '社团统计', reports: '举报处理', notifications: '站内通知', audit: '管理记录' };
  const statusLabels = {
    Draft: '草稿', Submitted: '待审核', Approved: '审核通过', Rejected: '已驳回',
    Published: '已发布', RegistrationOpen: '报名中', RegistrationClosed: '报名截止',
    InProgress: '进行中', Finished: '已结束', Archived: '已归档', Cancelled: '已取消',
    pending: '待审核', approved: '已通过', rejected: '已驳回', cancelled: '已取消',
    confirmed: '正式报名', waitlisted: '候补中', active: '正常', disabled: '已停用',
    todo: '待开始', in_progress: '进行中', done: '已完成',
    requested: '已申请', preparing: '准备中', ready: '已就绪', resolved: '已处理',
  };

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value === null || value === undefined || value === false) return;
      if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
      else if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'value') node.value = value;
      else if (key === 'checked') node.checked = Boolean(value);
      else if (key === 'disabled') node.disabled = Boolean(value);
      else node.setAttribute(key, value === true ? '' : String(value));
    });
    children.flat(Infinity).forEach(child => {
      if (child === null || child === undefined || child === false) return;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
    return node;
  }
  function button(text, action, variant = '', attrs = {}) {
    return el('button', { type: 'button', class: `btn ${variant}`, onclick: action, ...attrs }, text);
  }
  function badge(status) {
    const tone = ['RegistrationOpen', 'Approved', 'approved', 'confirmed', 'active', 'done', 'ready', 'resolved'].includes(status) ? 'green'
      : ['Submitted', 'pending', 'waitlisted', 'todo', 'Published', 'requested'].includes(status) ? 'amber'
        : ['Cancelled', 'Rejected', 'rejected', 'cancelled', 'disabled'].includes(status) ? 'red'
          : ['InProgress', 'in_progress', 'preparing'].includes(status) ? 'blue' : '';
    return el('span', { class: `status-badge ${tone}` }, statusLabels[status] || status || '未知状态');
  }
  function date(value, short = false) {
    if (!value) return '未设置';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '时间信息不可用';
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', ...(short ? {} : { hour: '2-digit', minute: '2-digit', hour12: false }) });
  }
  function localInput(value) {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function iso(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) throw new Error('请填写有效的日期与时间。');
    return d.toISOString();
  }
  const isStaff = () => state.user?.role === 'staff';
  const memberships = () => (state.user?.memberships || []).filter(m => m.active);
  const leaderClubs = () => memberships().filter(m => m.role === 'leader');
  const isLeader = clubId => leaderClubs().some(m => Number(m.club_id) === Number(clubId));
  const isMember = clubId => memberships().some(m => Number(m.club_id) === Number(clubId));
  const isStudent = () => state.user?.role === 'student';
  function toast(message, error = false) {
    const node = el('div', { class: `toast ${error ? 'error' : ''}` }, message);
    document.getElementById('toasts').append(node);
    setTimeout(() => node.remove(), 6500);
  }
  async function api(path, method = 'GET', body) {
    const options = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (method !== 'GET') options.headers['X-CSRF-Token'] = state.csrf;
    if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    let response;
    try { response = await fetch(path, options); } catch (_) { throw new Error('连接暂时中断，请检查网络后重试。'); }
    let payload;
    try { payload = await response.json(); } catch (_) { throw new Error('服务暂时无法响应，请稍后重试。'); }
    if (!response.ok || payload.error) {
      if (response.status === 401) {
        state.user = null;
        renderNavigation(); renderAccount();
      }
      throw new Error(payload.error?.message || `请求未完成（${response.status}）。`);
    }
    return payload.data;
  }
  async function session() {
    const result = await api('/api/session');
    state.user = result.user; state.csrf = result.csrf_token;
    await updateUnread();
    renderNavigation(); renderAccount();
  }
  async function updateUnread() {
    if (!state.user) { state.unread = 0; return; }
    try { state.unread = (await api('/api/notifications')).filter(n => !n.read).length; } catch (_) { state.unread = 0; }
  }
  function renderNavigation() {
    const items = [['activities', '◷'], ['clubs', '◇'], ['calendar', '▦']];
    if (isStudent()) items.push(['recommendations', '✧']);
    if (state.user) items.push(['dashboard', '▥'], ['todos', '☷'], ['records', '▤'], ['tasks', '✓']);
    if (isStaff() || leaderClubs().length) items.push(['resources', '⌑'], ['statistics', '▥']);
    if (isStaff()) items.push(['reports', '⚑']);
    if (state.user) items.push(['notifications', '◉']);
    if (isStaff()) items.push(['audit', '≡']);
    const nav = document.getElementById('navigation');
    nav.replaceChildren();
    items.forEach(([name, icon], index) => {
      if (index === 0) nav.append(el('div', { class: 'nav-group-label' }, '发现校园'));
      if (name === 'dashboard') nav.append(el('div', { class: 'nav-group-label' }, isStaff() ? '管理与协同' : '我的空间'));
      nav.append(el('a', { href: `#${name}`, class: `nav-link ${state.view === name ? 'active' : ''}`, ...(state.view === name ? { 'aria-current': 'page' } : {}) },
        el('span', { class: 'nav-icon', 'aria-hidden': 'true' }, icon), labels[name],
        name === 'notifications' && state.unread > 0 ? el('span', { class: 'nav-badge', 'aria-label': `${state.unread}条未读` }, state.unread > 99 ? '99+' : state.unread) : null));
    });
  }
  function renderAccount() {
    const account = document.getElementById('account');
    if (!state.user) {
      account.replaceChildren(el('span', { class: 'text-muted tiny' }, '欢迎来到校园空间'), button('登录 / 体验', () => loginDialog(), 'small'));
      return;
    }
    const role = isStaff() ? '管理中心工作人员' : leaderClubs().length ? '社团负责人' : memberships().length ? '社团成员' : '普通学生';
    account.replaceChildren(el('div', { class: 'account-details' }, el('div', { class: 'account-name' }, state.user.display_name), el('div', { class: 'account-role' }, role)),
      el('span', { class: 'avatar', 'aria-hidden': 'true' }, (state.user.display_name || '青').slice(-1)),
      el('button', { class: 'account-button', type: 'button', onclick: async event => {
        await perform(event.currentTarget, async () => { await api('/api/logout', 'POST'); await session(); location.hash = 'activities'; }, '已退出登录');
      } }, '退出'));
  }
  function heading(title, subtitle, action) { return el('div', { class: 'page-heading' }, el('div', {}, el('h1', {}, title), el('p', {}, subtitle)), action); }
  function section(title, count) { return el('div', { class: 'section-heading' }, el('h2', {}, title), count === undefined ? null : el('span', { class: 'count-label' }, `${count} 项`)); }
  function empty(title, subtitle = '', action) { return el('div', { class: 'empty-state' }, el('span', { class: 'empty-symbol', 'aria-hidden': 'true' }, '◇'), el('h3', {}, title), el('p', {}, subtitle), action); }
  function row(title, meta, actions = [], description) {
    return el('div', { class: 'list-row' }, el('div', { class: 'row-main' }, el('div', { class: 'row-title' }, title), el('div', { class: 'row-meta' }, meta), description ? el('div', { class: 'row-description' }, description) : null), el('div', { class: 'row-actions' }, actions));
  }
  function hero(type, count) {
    const club = type === 'clubs';
    return el('section', { class: 'hero' }, el('div', { class: 'hero-copy' },
      el('div', { class: 'eyebrow' }, club ? 'CLUB DIRECTORY / 社团发现' : 'CAMPUS ACTIVITIES / 活动广场'),
      el('h1', {}, club ? '找到你的同频伙伴，' : '让热爱，', el('br'), el('em', {}, club ? '从一个社团开始。' : '在校园发生。')),
      el('p', {}, club ? '在这里发现兴趣、认识伙伴，和喜欢的人一起，把平凡的校园日常过得有声有色。' : '走出教室，加入一场期待已久的活动。把好奇付诸行动，让每一次参与都成为值得收藏的校园记忆。')),
      el('div', { class: 'hero-summary' }, el('div', { class: 'hero-annotation' }, club ? '当前校园社团' : '当前列表活动'),
        el('div', { class: 'hero-count' }, el('strong', { class: 'hero-number' }, String(count).padStart(2, '0')), el('span', { class: 'hero-unit' }, club ? '个' : '场')),
        el('div', { class: 'hero-annotation' }, club ? '选择社团，查看介绍与申请方式' : '浏览详情，查看时间与报名状态')));
  }
  async function perform(control, work, message, refresh = true) {
    if (control) control.disabled = true;
    try {
      await work();
      if (message) toast(message);
      if (refresh) { await updateUnread(); renderNavigation(); await renderView(); }
      return true;
    } catch (error) { toast(error.message, true); return false; }
    finally { if (control?.isConnected) control.disabled = false; }
  }
  function dialog(title, subtitle = '', wide = false) {
    const existing = document.querySelector('dialog');
    if (existing) { existing.close(); existing.remove(); }
    const content = el('div', { class: 'dialog-content' });
    const node = el('dialog', { class: `dialog ${wide ? 'wide' : ''}`, 'aria-label': title },
      el('div', { class: 'dialog-header' }, el('div', {}, el('h2', {}, title), subtitle ? el('p', {}, subtitle) : null),
        el('button', { type: 'button', class: 'dialog-close', 'aria-label': '关闭窗口', onclick: () => node.close() }, '×')), content);
    node.addEventListener('close', () => node.remove());
    node.addEventListener('click', event => { if (event.target === node) { const r = node.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) node.close(); } });
    document.body.append(node); node.showModal();
    return { node, content };
  }
  function field(label, name, options = {}) {
    const id = `field-${name}-${Math.random().toString(36).slice(2, 8)}`;
    const { type = 'text', value = '', choices, help, ...attrs } = options;
    let input;
    if (choices) input = el('select', { id, name, ...attrs }, choices.map(choice => el('option', { value: choice.value }, choice.label)));
    else if (type === 'textarea') input = el('textarea', { id, name, rows: 4, ...attrs }, value);
    else input = el('input', { id, name, type, ...attrs });
    if (type !== 'textarea') input.value = value;
    return el('div', { class: 'field' }, el('label', { for: id }, label), input, help ? el('small', {}, help) : null);
  }
  function formSubmit(form, modal, submitText, handler, success) {
    const errorBox = el('div', { class: 'form-error', role: 'alert' });
    const submit = el('button', { type: 'submit', class: 'btn' }, submitText);
    form.append(errorBox, el('div', { class: 'form-actions' }, button('取消', () => modal.node.close(), 'secondary'), submit));
    form.addEventListener('submit', async event => {
      event.preventDefault(); errorBox.replaceChildren(); submit.disabled = true;
      try { await handler(new FormData(form)); modal.node.close(); if (success) toast(success); await session(); await renderView(); }
      catch (error) { errorBox.append(el('div', { class: 'error-box' }, error.message)); }
      finally { submit.disabled = false; }
    });
    return form;
  }
  function requireLogin() { if (state.user) return true; loginDialog(); return false; }

  function loginDialog() {
    const modal = dialog('登录校园空间', '登录后可报名活动、查看申请进度或管理所属社团。');
    const form = el('form', {});
    const username = field('账号', 'username', { value: 'student', required: true, autocomplete: 'username', maxlength: 80 });
    const password = field('密码', 'password', { type: 'password', value: 'Demo12345!', required: true, autocomplete: 'current-password', maxlength: 128 });
    const personas = [['student', '普通学生'], ['leader', '社团负责人'], ['member', '社团成员'], ['other_leader', '其他社团负责人'], ['staff', '管理中心工作人员']];
    const choices = el('div', { class: 'persona-grid', 'aria-label': '演示角色选择' });
    personas.forEach(([name, label]) => choices.append(el('button', { class: `persona ${name === 'student' ? 'active' : ''}`, type: 'button', onclick: event => {
      username.querySelector('input').value = name; password.querySelector('input').value = 'Demo12345!';
      choices.querySelectorAll('button').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
      event.currentTarget.classList.add('active'); event.currentTarget.setAttribute('aria-pressed', 'true');
    }, 'aria-pressed': name === 'student' ? 'true' : 'false' }, label, el('small', {}, name))));
    form.append(el('div', { class: 'login-intro' }, el('div', { class: 'login-mark', 'aria-hidden': 'true' }, '禾'), el('h3', {}, '欢迎来到青禾'), el('p', {}, '发现新活动，管理社团，记录每一次参与。')),
      el('div', { class: 'disclosure' }, '课程演示账号仅在演示数据初始化后可用。选择一个角色即可体验；演示口令为 Demo12345!，不用于真实校园账号。'), choices, username, password);
    modal.content.append(formSubmit(form, modal, '进入校园空间', async data => {
      const result = await api('/api/login', 'POST', { username: data.get('username'), password: data.get('password') });
      state.user = result.user; state.csrf = result.csrf_token;
    }, '登录成功，欢迎回来'));
  }

  function activityCard(activity, index) {
    return el('article', { class: 'activity-card' },
      el('div', { class: `card-visual tone-${index % 3}`, 'aria-hidden': 'true' }, el('span', { class: 'theme-chip' }, activity.theme || '校园活动'), el('span', { class: 'visual-symbol' }, ['遇', '悦', '行'][index % 3])),
      el('div', { class: 'card-body' }, el('div', { class: 'card-club' }, el('span', { 'aria-hidden': 'true' }, '◇'), activity.club_name), el('h3', {}, activity.title),
        el('div', { class: 'card-meta' }, el('span', { class: 'icon', 'aria-hidden': 'true' }, '◷'), date(activity.start_time)),
        el('div', { class: 'card-meta' }, el('span', { class: 'icon', 'aria-hidden': 'true' }, '⌖'), activity.location)),
      el('div', { class: 'card-footer' }, el('div', {}, badge(activity.status), el('div', { class: 'capacity-note' }, `${activity.registered_count || 0} / ${activity.capacity} 人报名${activity.waitlist_count ? ` · ${activity.waitlist_count} 人候补` : ''}`)), button('查看活动 ↗', () => activityDetail(activity.id), 'ghost small')));
  }
  async function activitiesView() {
    const query = new URLSearchParams();
    Object.entries(state.filters).forEach(([key, value]) => { if (value) query.set(key, value); });
    if (state.filters.date) query.set('utc_offset', String(-new Date(`${state.filters.date}T12:00:00`).getTimezoneOffset()));
    const [activities, clubs] = await Promise.all([api(`/api/activities${query.size ? `?${query}` : ''}`), api('/api/clubs')]);
    if (!query.size) state.themes = [...new Set(activities.map(a => a.theme).filter(Boolean))];
    const search = el('input', { type: 'search', name: 'q', placeholder: '搜索活动名称或关键词', value: state.filters.q, 'aria-label': '搜索活动' });
    const theme = el('select', { name: 'theme', 'aria-label': '活动主题' }, el('option', { value: '' }, '所有主题'), state.themes.map(t => el('option', { value: t }, t))); theme.value = state.filters.theme;
    const club = el('select', { name: 'club_id', 'aria-label': '活动所属社团' }, el('option', { value: '' }, '所有社团'), clubs.map(c => el('option', { value: c.id }, c.name))); club.value = state.filters.club_id;
    const day = el('input', { type: 'date', name: 'date', value: state.filters.date, 'aria-label': '活动开始日期' });
    const toolbar = el('form', { class: 'toolbar', onsubmit: event => { event.preventDefault(); state.filters = Object.fromEntries(new FormData(toolbar)); renderView(); } },
      el('div', { class: 'search-field' }, el('span', { class: 'search-icon', 'aria-hidden': 'true' }, '⌕'), search), theme, club, day, el('button', { type: 'submit', class: 'btn' }, '筛选'));
    const any = Object.values(state.filters).some(Boolean);
    if (any) toolbar.append(button('重置', () => { state.filters = { q: '', theme: '', club_id: '', date: '' }; renderView(); }, 'ghost'));
    return el('div', {}, hero('activities', activities.length), section('公开活动', activities.length), toolbar,
      activities.length ? el('div', { class: 'card-grid' }, activities.map(activityCard)) : empty('暂时没有符合条件的活动', any ? '请尝试其他主题或日期。' : '当前还没有已发布的活动。'));
  }
  function dayKey(value) {
    const d = value instanceof Date ? value : new Date(value);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }
  async function calendarView() {
    const activities = await api('/api/activities');
    const month = state.calendarMonth;
    const year = month.getFullYear(), index = month.getMonth();
    const monthDays = new Date(year, index + 1, 0).getDate();
    const firstWeekday = (month.getDay() + 6) % 7;
    const groups = new Map();
    activities.forEach(a => { const key = dayKey(a.start_time); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(a); });
    const monthPrefix = dayKey(month).slice(0, 7);
    if (!state.calendarDay.startsWith(monthPrefix)) {
      const today = dayKey(new Date());
      state.calendarDay = today.startsWith(monthPrefix) ? today : [...groups.keys()].filter(k => k.startsWith(monthPrefix)).sort()[0] || dayKey(month);
    }
    const shift = offset => { state.calendarMonth = new Date(year, index + offset, 1); state.calendarDay = ''; renderView(); };
    const header = el('div', { class: 'calendar-heading' }, el('h2', {}, `${year} 年 ${index + 1} 月`), el('div', { class: 'action-row' },
      button('‹', () => shift(-1), 'secondary small', { 'aria-label': '上个月' }), button('本月', () => { state.calendarMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1); state.calendarDay = dayKey(new Date()); renderView(); }, 'secondary small'), button('›', () => shift(1), 'secondary small', { 'aria-label': '下个月' })));
    const grid = el('div', { class: 'calendar-grid', 'aria-label': `${year}年${index + 1}月活动日期` });
    ['一', '二', '三', '四', '五', '六', '日'].forEach(w => grid.append(el('div', { class: 'calendar-weekday' }, w)));
    for (let n = 0; n < firstWeekday; n++) grid.append(el('div', { class: 'calendar-blank', 'aria-hidden': 'true' }));
    for (let n = 1; n <= monthDays; n++) {
      const key = dayKey(new Date(year, index, n)), dayActivities = groups.get(key) || [];
      grid.append(el('button', { type: 'button', class: `calendar-day ${key === state.calendarDay ? 'selected' : ''} ${key === dayKey(new Date()) ? 'today' : ''}`, 'aria-pressed': key === state.calendarDay ? 'true' : 'false', 'aria-label': `${index + 1}月${n}日，${dayActivities.length}场活动`, onclick: () => { state.calendarDay = key; renderView(); } },
        el('span', { class: 'calendar-day-number' }, n), dayActivities.length ? el('span', { class: 'calendar-event-count' }, `${dayActivities.length} 场`) : null,
        el('span', { class: 'calendar-preview', 'aria-hidden': 'true' }, dayActivities.slice(0, 2).map(a => el('span', {}, a.title)))));
    }
    const selected = groups.get(state.calendarDay) || [];
    return el('div', {}, heading('活动日历', '活动按开始日显示，日期和时间按本地时区显示。'), el('div', { class: 'panel' }, header, grid),
      section(`${Number(state.calendarDay.slice(5, 7))} 月 ${Number(state.calendarDay.slice(8))} 日的活动`, selected.length),
      selected.length ? el('div', { class: 'card-grid' }, selected.map(activityCard)) : empty('这一天暂时没有活动', '可切换日期查看其他活动。'));
  }
  async function recommendationsView() {
    const [activities, all] = await Promise.all([api(`/api/recommendations${state.preferredThemes.length ? `?${new URLSearchParams({ themes: state.preferredThemes.join(',') })}` : ''}`), api('/api/activities')]);
    const themes = [...new Set(all.map(a => a.theme).filter(Boolean))];
    const form = el('form', { onsubmit: event => { event.preventDefault(); state.preferredThemes = new FormData(form).getAll('themes'); renderView(); } });
    form.append(el('div', { class: 'interest-options' }, themes.map(t => el('label', { class: 'interest-option' }, el('input', { name: 'themes', type: 'checkbox', value: t, checked: state.preferredThemes.includes(t) }), el('span', {}, t)))),
      el('div', { class: 'action-row' }, el('button', { type: 'submit', class: 'btn small' }, '更新兴趣推荐'), state.preferredThemes.length ? button('清除偏好', () => { state.preferredThemes = []; renderView(); }, 'ghost small') : null));
    return el('div', {}, heading('兴趣推荐', '选择感兴趣的主题，查看匹配的公开活动。'), el('div', { class: 'panel' }, el('h2', {}, '选择活动主题'), themes.length ? form : el('p', {}, '新活动发布后，你可以在这里选择兴趣方向。'), el('div', { class: 'info-box' }, '推荐按所选主题匹配优先排序，其次按活动开始时间排序。未选择偏好时，仅按开始时间排序。')),
      section('推荐活动', activities.length), activities.length ? el('div', { class: 'recommendation-grid card-grid' }, activities.map((a, i) => el('div', { class: 'recommended-item' }, activityCard(a, i), el('p', { class: 'recommendation-reason' }, a.recommendation_reason || '按活动时间排序')))) : empty('暂无推荐活动', '当前暂无可推荐的公开活动。'));
  }
  async function clubsView() {
    const clubs = await api('/api/clubs');
    const action = isStudent() ? button('＋ 申请成立社团', () => filingDialog(), 'secondary small') : null;
    return el('div', {}, hero('clubs', clubs.length), el('div', { class: 'section-heading' }, el('h2', {}, '校园社团'), action),
      clubs.length ? el('div', { class: 'card-grid' }, clubs.map((club, index) => el('article', { class: 'club-card' },
        el('div', { class: 'club-icon', 'aria-hidden': 'true' }, ['影', '书', '趣'][index % 3]), el('h3', {}, club.name), el('p', {}, club.description),
        el('div', { class: 'card-actions' }, badge(club.status), button('了解社团 ↗', () => clubDetail(club.id), 'ghost small'))))) : empty('暂无社团记录', '社团资料录入后会显示在这里。'));
  }
  async function clubDetail(id) {
    const modal = dialog('社团介绍'); modal.content.append(el('div', { class: 'loading-state' }, '正在获取社团信息…'));
    try {
      const club = await api(`/api/clubs/${id}`);
      if (!modal.node.isConnected) return;
      modal.content.replaceChildren(el('h3', { class: 'detail-title' }, club.name), el('div', { class: 'detail-subtitle' }, badge(club.status), `负责人：${club.leader_name || '尚未指定'}`),
        el('p', { class: 'detail-description' }, club.description));
      const actions = el('div', { class: 'detail-actions' });
      if (!state.user) actions.append(button('登录后申请加入', () => loginDialog()));
      else if (isStudent() && !isMember(id) && club.status === 'active') actions.append(button('申请加入社团', () => applicationDialog(club)));
      else if (isMember(id)) modal.content.append(el('div', { class: 'info-box' }, isLeader(id) ? '你是这个社团的负责人，可在工作台管理成员和活动。' : '你已加入这个社团。可以参与社团活动和筹备协作。'));
      if (isLeader(id)) { actions.append(button('成员与入社申请', () => membershipDialog(club), 'secondary')); actions.append(button('创建社团活动', () => activityForm(null, id), 'secondary')); }
      if (isStaff()) actions.append(button('社团管理', () => governanceDialog(club), 'secondary'));
      actions.append(button('浏览社团活动', () => { modal.node.close(); state.filters = { q: '', theme: '', club_id: String(id), date: '' }; location.hash = 'activities'; renderView(); }, 'ghost'));
      modal.content.append(actions);
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  function applicationDialog(club) {
    if (!requireLogin()) return;
    const modal = dialog('申请加入社团', club.name);
    const form = el('form', {}, field('简单介绍自己和想加入的理由', 'message', { type: 'textarea', required: true, maxlength: 1000, placeholder: '简要说明兴趣、相关经历和申请理由。' }));
    modal.content.append(formSubmit(form, modal, '提交申请', data => api(`/api/clubs/${club.id}/applications`, 'POST', { message: data.get('message') }), '入社申请已提交，可在“我的参与”查看进度'));
  }
  function filingDialog() {
    if (!requireLogin()) return;
    const modal = dialog('申请成立社团', '由拟任负责人或社团申请人提交，管理中心审核通过后建立正式社团。');
    const form = el('form', {}, field('社团名称', 'name', { required: true, maxlength: 120 }), field('社团介绍与成立目的', 'description', { type: 'textarea', required: true, maxlength: 2000, placeholder: '介绍社团的兴趣方向、计划开展的活动和成立目的。' }));
    modal.content.append(formSubmit(form, modal, '提交备案申请', data => api('/api/club-registrations', 'POST', { name: data.get('name'), description: data.get('description') }), '社团备案申请已提交'));
  }
  async function membershipDialog(club) {
    const modal = dialog('成员与入社申请', club.name, true); modal.content.append(el('div', { class: 'loading-state' }, '正在获取成员信息…'));
    try {
      const [applications, members] = await Promise.all([api(`/api/clubs/${club.id}/applications`), api(`/api/clubs/${club.id}/members`)]);
      if (!modal.node.isConnected) return;
      const pending = applications.filter(a => a.status === 'pending');
      modal.content.replaceChildren(section('待处理的入社申请', pending.length));
      modal.content.append(pending.length ? el('div', { class: 'list' }, pending.map(a => row(a.display_name || a.applicant_name || '申请学生', '希望加入社团', [
        button('通过', event => perform(event.currentTarget, () => api(`/api/applications/${a.id}/review`, 'POST', { decision: 'approve', reason: '' }), '已通过入社申请').then(ok => { if (ok) membershipDialog(club); }), 'small'),
        button('驳回', () => reviewDialog('入社申请', `/api/applications/${a.id}/review`, 'reject', () => membershipDialog(club)), 'danger small')], a.message))) : empty('入社申请已处理完毕', '有新的申请时，会显示在这里。'));
      modal.content.append(section('社团成员', members.length), el('div', { class: 'list' }, members.map(m => row(m.display_name, `${m.role === 'leader' ? '社团负责人' : '社团成员'} · ${m.active ? '有效成员' : '已停用'}`, m.role === 'leader' ? [] : [button(m.active ? '停用成员' : '恢复成员', event => perform(event.currentTarget, () => api(`/api/clubs/${club.id}/members/${m.id}`, 'PATCH', { active: !m.active }), m.active ? '成员已停用' : '成员已恢复').then(ok => { if (ok) membershipDialog(club); }), m.active ? 'danger small' : 'secondary small')]))));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  async function governanceDialog(club) {
    const modal = dialog('社团管理', `当前负责人：${club.leader_name || '尚未指定'}`);
    modal.content.append(el('div', { class: 'loading-state' }, '正在获取有效成员…'));
    try {
      const members = await api(`/api/clubs/${club.id}/members`);
      if (!modal.node.isConnected) return;
      const statusForm = el('form', {}, field('社团状态', 'status', { choices: [{ value: 'active', label: '正常' }, { value: 'disabled', label: '停用' }], value: club.status, help: '停用后暂停社团业务操作，历史记录仍保留。' }));
      const candidates = members.filter(m => m.active);
      const leaderForm = el('form', {}, field('确认新负责人', 'leader_id', { required: true, choices: [{ value: '', label: '请选择有效社团成员' }, ...candidates.map(m => ({ value: m.user_id, label: `${m.display_name}${m.role === 'leader' ? '（现任负责人）' : ''}` }))], help: '负责人变更由管理中心确认，并记录变更信息。' }));
      modal.content.replaceChildren(el('div', { class: 'info-box' }, '管理中心可管理各社团的状态与负责人。新负责人须为本社团的有效成员。'),
        el('h3', { class: 'detail-section-title' }, '社团状态'), formSubmit(statusForm, modal, '保存社团状态', data => api(`/api/clubs/${club.id}/governance`, 'PATCH', { status: data.get('status') }), '社团状态已更新'),
        el('h3', { class: 'detail-section-title' }, '负责人变更'), formSubmit(leaderForm, modal, '确认负责人变更', data => api(`/api/clubs/${club.id}/governance`, 'PATCH', { leader_id: Number(data.get('leader_id')) }), '社团负责人已更新'));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }

  function activityActions(activity) {
    const result = [];
    const action = (name, label, variant = 'secondary small') => result.push(button(label, event => {
      if (['reject', 'cancel'].includes(name)) { reasonTransition(activity, name); return; }
      perform(event.currentTarget, () => api(`/api/activities/${activity.id}/transition`, 'POST', { action: name }), `活动已${{ submit: '提交审核', approve: '审核通过', publish: '发布', open_registration: '开放报名', archive: '归档' }[name] || '更新'}`).then(ok => { if (ok && document.querySelector('dialog')) activityDetail(activity.id); });
    }, variant));
    if (isStaff() && activity.status === 'Submitted') { action('approve', '审核通过', 'small'); action('reject', '驳回', 'danger small'); }
    if (isLeader(activity.club_id)) {
      if (['Draft', 'Rejected'].includes(activity.status)) result.push(button('编辑', () => activityForm(activity), 'secondary small'));
      if (activity.status === 'Draft') action('submit', '提交审核', 'small');
      if (activity.status === 'Approved') action('publish', '发布活动', 'small');
      if (activity.status === 'Published') action('open_registration', '开放报名', 'small');
      if (['Published', 'RegistrationOpen', 'RegistrationClosed'].includes(activity.status)) action('cancel', '取消活动', 'danger small');
      if (activity.status === 'Finished') action('archive', '归档', 'secondary small');
    }
    return result;
  }
  function reasonTransition(activity, action) {
    const cancel = action === 'cancel';
    const modal = dialog(cancel ? '取消活动' : '驳回活动', activity.title);
    const form = el('form', {}, el('div', { class: 'info-box' }, cancel ? '取消后会通知已报名的学生，活动不再开放参与。' : '请说明需调整的内容，让社团负责人能够完善活动。'), field(cancel ? '取消原因' : '驳回原因', 'reason', { type: 'textarea', required: true, maxlength: 1000 }));
    modal.content.append(formSubmit(form, modal, cancel ? '确认取消' : '确认驳回', data => api(`/api/activities/${activity.id}/transition`, 'POST', { action, reason: data.get('reason') }), cancel ? '活动已取消' : '活动已驳回'));
  }
  async function activityDetail(id) {
    const modal = dialog('活动详情', '', true); modal.content.append(el('div', { class: 'loading-state' }, '正在获取活动信息…'));
    try {
      const a = await api(`/api/activities/${id}`);
      if (!modal.node.isConnected) return;
      const detail = el('dl', { class: 'detail-grid' });
      [['活动时间', `${date(a.start_time)} — ${date(a.end_time)}`], ['活动地点', a.location], ['报名截止', date(a.registration_deadline)], ['报名人数', `${a.registered_count || 0} / ${a.capacity} 人${a.waitlist_enabled ? ` · 候补 ${a.waitlist_count || 0} 人` : ''}`]].forEach(([name, value]) => detail.append(el('div', {}, el('dt', {}, name), el('dd', {}, value))));
      modal.content.replaceChildren(el('h3', { class: 'detail-title' }, a.title), el('div', { class: 'detail-subtitle' }, badge(a.status), a.club_name, el('span', { class: 'theme-chip' }, a.theme)), detail,
        el('h4', { class: 'detail-section-title' }, '关于这次活动'), el('p', { class: 'detail-description' }, a.description));
      if (a.review_reason && a.status === 'Rejected') modal.content.append(el('div', { class: 'error-box' }, `审核反馈：${a.review_reason}`));
      const actions = el('div', { class: 'detail-actions' }, activityActions(a));
      if (!state.user && a.status === 'RegistrationOpen') actions.append(button('登录后报名', () => loginDialog()));
      const registration = a.my_registration;
      if (isStudent() && (!registration || registration.status === 'cancelled') && a.status === 'RegistrationOpen') {
        const waitlist = a.registered_count >= a.capacity;
        if (!waitlist || a.waitlist_enabled) actions.append(button(waitlist ? '加入候补名单' : '报名参加', event => perform(event.currentTarget, () => api(`/api/activities/${id}/registrations`, 'POST', {}), waitlist ? '已加入候补。报名开放且未截止时，如有名额将按顺序转正。' : '报名成功，可在“我的参与”查看记录。').then(ok => { if (ok) activityDetail(id); })));
        else modal.content.append(el('div', { class: 'info-box' }, '本次活动名额已满，暂不开放候补。'));
      }
      if (registration && ['confirmed', 'waitlisted'].includes(registration.status)) {
        modal.content.append(el('div', { class: 'info-box' }, registration.checked_in ? '你已完成本次活动签到。' : registration.status === 'waitlisted' ? '你已加入候补。报名开放且未截止时，如有名额将按顺序转正并通知。' : '你已成功报名。活动开始后，请联系现场社团工作人员登记签到。'));
        if (!registration.checked_in && new Date() < new Date(a.registration_deadline)) actions.append(button('取消报名', event => perform(event.currentTarget, () => api(`/api/registrations/${registration.id}/cancel`, 'POST', {}), '报名已取消').then(ok => { if (ok) activityDetail(id); }), 'danger'));
      }
      if (isLeader(a.club_id)) {
        actions.append(button('报名与签到', () => rosterDialog(a), 'secondary'));
        if (!['Cancelled', 'Finished', 'Archived'].includes(a.status)) actions.append(button('安排筹备任务', () => taskForm(a), 'secondary'));
        if (['Submitted', 'Approved', 'Published', 'RegistrationOpen', 'RegistrationClosed', 'InProgress'].includes(a.status)) actions.append(button('申请活动场地', () => venueForm(a), 'secondary'));
      }
      else if (isMember(a.club_id) && a.status === 'InProgress') actions.append(button('现场签到登记', () => rosterDialog(a), 'secondary'));
      if (isLeader(a.club_id) || isStaff()) actions.append(button('活动物资', () => materialsDialog(a), 'secondary'));
      if (isStudent() && registration?.checked_in && ['Finished', 'Archived'].includes(a.status)) {
        if (a.my_feedback) modal.content.append(el('div', { class: 'info-box' }, `你已评价这次活动：${a.my_feedback.rating} / 5 分${a.my_feedback.comment ? `。${a.my_feedback.comment}` : '。'}`));
        else actions.append(button('评价本次活动', () => feedbackDialog(a)));
      }
      if (isStudent() && ['Published', 'RegistrationOpen', 'RegistrationClosed', 'InProgress', 'Finished', 'Archived', 'Cancelled'].includes(a.status)) actions.append(button('举报活动', () => reportDialog(a), 'ghost'));
      modal.content.append(actions);
      if (['RegistrationClosed', 'Finished', 'Archived', 'Cancelled'].includes(a.status) && (!registration || registration.status === 'cancelled')) modal.content.append(el('div', { class: 'info-box' }, a.status === 'Cancelled' ? '这次活动已取消。欢迎继续发现其他校园活动。' : '本次活动的报名已结束。'));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  function activityForm(activity = null, selectedClub = null) {
    const clubs = leaderClubs();
    if (!clubs.length) { toast('只有社团负责人可以创建活动。', true); return; }
    const modal = dialog(activity ? '编辑活动草稿' : '创建社团活动', '保存草稿后提交管理中心审核，审核通过后可发布并开放报名。', true);
    const a = activity || {};
    const form = el('form', {},
      el('div', { class: 'form-grid' }, field('所属社团', 'club_id', { value: a.club_id || selectedClub || clubs[0].club_id, choices: clubs.map(c => ({ value: c.club_id, label: c.club_name })), required: true, ...(activity ? { disabled: true } : {}) }), field('活动主题', 'theme', { value: a.theme || '', required: true, maxlength: 80, placeholder: '如：艺术、阅读、体育' })),
      field('活动名称', 'title', { value: a.title || '', required: true, maxlength: 120, placeholder: '填写活动名称' }),
      field('活动介绍', 'description', { type: 'textarea', value: a.description || '', required: true, maxlength: 2000, placeholder: '说明活动内容、参与方式和需要准备的事项。' }),
      el('div', { class: 'form-grid' }, field('活动地点', 'location', { value: a.location || '', required: true, maxlength: 120 }), field('参与名额', 'capacity', { type: 'number', value: a.capacity || 30, required: true, min: 1, max: 10000, step: 1 })),
      el('div', { class: 'form-grid' }, field('开始时间', 'start_time', { type: 'datetime-local', value: localInput(a.start_time), required: true }), field('结束时间', 'end_time', { type: 'datetime-local', value: localInput(a.end_time), required: true })),
      field('报名截止时间', 'registration_deadline', { type: 'datetime-local', value: localInput(a.registration_deadline), required: true, help: '截止时间应不晚于活动开始时间。时间按你所在的本地时区填写。' }),
      el('label', { class: 'check-field' }, el('input', { name: 'waitlist_enabled', type: 'checkbox', checked: a.waitlist_enabled ?? true }), '名额已满时允许候补；报名开放且未截止时按顺序转正'));
    modal.content.append(formSubmit(form, modal, '保存草稿', data => {
      const body = { club_id: Number(a.club_id || data.get('club_id')), title: data.get('title'), theme: data.get('theme'), description: data.get('description'), location: data.get('location'), capacity: Number(data.get('capacity')), start_time: iso(data.get('start_time')), end_time: iso(data.get('end_time')), registration_deadline: iso(data.get('registration_deadline')), waitlist_enabled: data.has('waitlist_enabled') };
      return api(activity ? `/api/activities/${activity.id}` : '/api/activities', activity ? 'PATCH' : 'POST', body);
    }, '活动草稿已保存，可在工作台提交审核'));
  }
  async function rosterDialog(activity) {
    const modal = dialog('报名与现场签到', activity.title, true); modal.content.append(el('div', { class: 'loading-state' }, '正在获取报名名单…'));
    try {
      const registrations = await api(`/api/activities/${activity.id}/registrations`);
      if (!modal.node.isConnected) return;
      modal.content.replaceChildren(el('div', { class: 'info-box' }, activity.status === 'InProgress' ? '活动进行中。确认学生已到场后登记签到；仅正式报名的学生可以签到。' : '活动开始后可登记现场签到。目前可以查看正式报名和候补名单。'));
      if (!registrations.length) { modal.content.append(empty('还没有报名记录', '开放报名后，报名与候补信息将显示在这里。')); return; }
      const table = el('table', {}, el('thead', {}, el('tr', {}, ['学生', '报名状态', '签到情况', '操作'].map(t => el('th', { scope: 'col' }, t)))), el('tbody', {}, registrations.map(r => el('tr', {},
        el('td', {}, r.display_name), el('td', {}, badge(r.status)), el('td', {}, r.checked_in ? '已签到' : '未签到'),
        el('td', {}, r.status === 'confirmed' && !r.checked_in && activity.status === 'InProgress' ? button('确认到场', event => perform(event.currentTarget, () => api(`/api/activities/${activity.id}/check-ins`, 'POST', { user_id: r.user_id }), '签到已登记').then(ok => { if (ok) rosterDialog(activity); }), 'small') : '—')))));
      modal.content.append(el('div', { class: 'table-wrap' }, table));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  async function taskForm(activity) {
    const modal = dialog('安排筹备任务', activity.title); modal.content.append(el('div', { class: 'loading-state' }, '正在获取社团成员…'));
    try {
      const members = (await api(`/api/clubs/${activity.club_id}/members`)).filter(m => m.active);
      if (!modal.node.isConnected) return;
      const form = el('form', {}, field('任务名称', 'title', { required: true, maxlength: 120, placeholder: '如：确认现场物料、布置活动场地' }),
        field('任务负责人', 'assignee_id', { required: true, choices: [{ value: '', label: '选择本社团成员' }, ...members.map(m => ({ value: m.user_id, label: m.display_name }))] }),
        field('完成期限', 'due_time', { type: 'datetime-local', required: true, value: localInput(activity.start_time) }));
      modal.content.replaceChildren(formSubmit(form, modal, '创建并分配任务', data => api(`/api/activities/${activity.id}/tasks`, 'POST', { title: data.get('title'), assignee_id: Number(data.get('assignee_id')), due_time: iso(data.get('due_time')) }), '筹备任务已安排，负责人会收到通知'));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  async function venueForm(activity = null) {
    const modal = dialog('申请活动场地', activity ? activity.title : '选择社团活动，再填写使用时间。');
    modal.content.append(el('div', { class: 'loading-state' }, '正在获取可申请场地…'));
    try {
      const [venues, allActivities] = await Promise.all([api('/api/venues'), activity ? Promise.resolve([activity]) : api('/api/my/activities')]);
      const allowed = allActivities.filter(a => ['Submitted', 'Approved', 'Published', 'RegistrationOpen', 'RegistrationClosed', 'InProgress'].includes(a.status));
      if (!modal.node.isConnected) return;
      if (!allowed.length || !venues.length) { modal.content.replaceChildren(empty(!allowed.length ? '暂无可申请场地的活动' : '暂无可申请场地', !allowed.length ? '先创建活动并提交审核，再申请活动期间需要的场地。' : '请联系管理中心了解可使用的校园场地。')); return; }
      const current = allowed[0];
      const activityField = field('所属活动', 'activity_id', { value: current.id, choices: allowed.map(a => ({ value: a.id, label: `${a.title} · ${a.club_name}` })), required: true });
      const availableStart = a => localInput(new Date(Math.ceil(Math.max(new Date(a.start_time).getTime(), Date.now() + 60000) / 60000) * 60000).toISOString());
      const startField = field('场地使用开始时间', 'start_time', { type: 'datetime-local', value: availableStart(current), required: true });
      const endField = field('场地使用结束时间', 'end_time', { type: 'datetime-local', value: localInput(current.end_time), required: true });
      activityField.querySelector('select').addEventListener('change', event => {
        const chosen = allowed.find(a => Number(a.id) === Number(event.target.value));
        startField.querySelector('input').value = availableStart(chosen); endField.querySelector('input').value = localInput(chosen.end_time);
      });
      const form = el('form', {}, activityField, field('校园场地', 'venue_id', { value: venues[0].id, required: true, choices: venues.map(v => ({ value: v.id, label: v.name })) }),
        el('div', { class: 'form-grid' }, startField, endField), el('div', { class: 'info-box' }, '使用开始时间不得早于当前时间，且使用时段须落在活动期间。管理中心审批时会检查已批准时段，避免同一场地发生时间冲突。'));
      modal.content.replaceChildren(formSubmit(form, modal, '提交场地申请', data => api(`/api/activities/${Number(data.get('activity_id'))}/venue-applications`, 'POST', { venue_id: Number(data.get('venue_id')), start_time: iso(data.get('start_time')), end_time: iso(data.get('end_time')) }), '场地申请已提交，可在“活动资源”查看审批进度'));
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  async function materialsDialog(activity) {
    const modal = dialog('活动物资', activity.title); modal.content.append(el('div', { class: 'loading-state' }, '正在获取物资清单…'));
    try {
      const materials = await api(`/api/activities/${activity.id}/materials`);
      if (!modal.node.isConnected) return;
      const writable = isLeader(activity.club_id) && !['Cancelled', 'Finished', 'Archived'].includes(activity.status);
      modal.content.replaceChildren(el('div', { class: 'info-box' }, '记录活动需要的物资与准备进度，供社团负责人协调筹备。'));
      if (!materials.length) modal.content.append(empty('物资清单暂时为空', writable ? '添加活动需要的物资，再跟进准备进度。' : '社团负责人添加的活动物资会显示在这里。'));
      else modal.content.append(el('div', { class: 'list' }, materials.map(m => {
        const select = el('select', { 'aria-label': `${m.name}的物资状态`, onchange: event => {
          const control = event.currentTarget;
          perform(control, () => api(`/api/materials/${m.id}`, 'PATCH', { status: control.value }), '物资准备进度已更新').then(ok => { if (ok) materialsDialog(activity); else control.value = m.status; });
        } }, ['requested', 'preparing', 'ready'].map(s => el('option', { value: s }, statusLabels[s])));
        select.value = m.status;
        return row(m.name, `数量：${m.quantity}`, writable ? [select] : [badge(m.status)]);
      })));
      if (writable) {
        const form = el('form', {}, el('h3', { class: 'detail-section-title' }, '添加所需物资'), el('div', { class: 'form-grid' }, field('物资名称', 'name', { required: true, maxlength: 120, placeholder: '如：签到笔、展板' }), field('数量', 'quantity', { type: 'number', value: 1, min: 1, max: 10000, step: 1, required: true })));
        modal.content.append(formSubmit(form, modal, '添加物资', data => api(`/api/activities/${activity.id}/materials`, 'POST', { name: data.get('name'), quantity: Number(data.get('quantity')) }), '活动物资已添加'));
      }
    } catch (error) { if (modal.node.isConnected) modal.content.replaceChildren(el('div', { class: 'error-box' }, error.message)); }
  }
  function feedbackDialog(activity) {
    const modal = dialog('评价本次活动', activity.title);
    const form = el('form', {}, el('div', { class: 'info-box' }, '活动结束后，已签到学生可提交一次评价。'),
      field('总体评分', 'rating', { value: '5', required: true, choices: [{ value: '5', label: '5 分 · 非常满意' }, { value: '4', label: '4 分 · 满意' }, { value: '3', label: '3 分 · 一般' }, { value: '2', label: '2 分 · 不太满意' }, { value: '1', label: '1 分 · 不满意' }] }), field('评价与建议', 'comment', { type: 'textarea', maxlength: 2000, placeholder: '你喜欢哪些环节？还有哪些地方可以改进？' }));
    modal.content.append(formSubmit(form, modal, '提交活动评价', data => api(`/api/activities/${activity.id}/feedback`, 'POST', { rating: Number(data.get('rating')), comment: data.get('comment') }), '评价已提交，感谢反馈。'));
  }
  function reportDialog(activity) {
    const modal = dialog('举报活动', activity.title);
    const form = el('form', {}, el('div', { class: 'info-box' }, '请说明需要管理中心关注的具体问题。处理结果可在“我的参与”中的举报记录查看。'), field('举报原因', 'reason', { type: 'textarea', required: true, maxlength: 2000, placeholder: '描述活动存在的问题和相关情况。' }));
    modal.content.append(formSubmit(form, modal, '提交举报', data => api(`/api/activities/${activity.id}/reports`, 'POST', { reason: data.get('reason') }), '举报已提交给管理中心'));
  }
  function resolveReportDialog(report) {
    const modal = dialog('处理活动举报', report.activity_title);
    const form = el('form', {}, el('div', { class: 'info-box' }, `举报原因：${report.reason}`), field('处理结果与说明', 'resolution', { type: 'textarea', required: true, maxlength: 2000, placeholder: '记录核查情况和已采取的处理措施。' }));
    modal.content.append(formSubmit(form, modal, '确认处理完成', data => api(`/api/reports/${report.id}/resolve`, 'POST', { resolution: data.get('resolution') }), '举报处理结果已记录'));
  }
  function reviewDialog(name, endpoint, decision, after) {
    const modal = dialog(`驳回${name}`, '请记录具体原因，方便申请人修改。');
    const form = el('form', {}, field('驳回原因', 'reason', { type: 'textarea', required: true, maxlength: 1000 }));
    modal.content.append(formSubmit(form, modal, '确认驳回', async data => {
      await api(endpoint, 'POST', { decision, reason: data.get('reason') });
      if (after) setTimeout(after, 150);
    }, `${name}已驳回`));
  }

  function activityRow(a) { return row(a.title, `${a.club_name} · ${date(a.start_time)} · ${a.location}`, [badge(a.status), button('详情', () => activityDetail(a.id), 'ghost small'), ...activityActions(a)], a.status === 'Rejected' && a.review_reason ? `审核反馈：${a.review_reason}` : null); }
  async function dashboardView() {
    const user = state.user;
    const staff = isStaff();
    const [activities, filings, tasks, clubs] = await Promise.all([
      staff || leaderClubs().length ? api('/api/my/activities') : Promise.resolve([]),
      api('/api/club-registrations'), api('/api/tasks'), staff ? api('/api/clubs') : Promise.resolve([]),
    ]);
    const pendingActivities = activities.filter(a => a.status === 'Submitted');
    const pendingFilings = filings.filter(f => f.status === 'pending');
    const result = el('div', {}, heading(staff ? '社团管理中心' : '我的工作台', staff ? '处理活动审核、社团备案、场地申请和举报。' : '查看所属社团、活动报名和待办任务。', !staff && leaderClubs().length ? button('＋ 创建活动', () => activityForm()) : null),
      el('div', { class: 'welcome-strip' }, el('div', {}, el('h2', {}, `${user.display_name}，你好。`), el('p', {}, staff ? '待审核和待处理的事项见下方列表。' : leaderClubs().length ? '管理社团成员、活动与筹备任务。' : '查看近期报名、社团和筹备任务。')), button('浏览校园活动 ↗', () => { location.hash = 'activities'; }, 'ghost')));
    if (staff) {
      result.append(el('div', { class: 'action-row dashboard-shortcuts' }, button('查看待办事项', () => { location.hash = 'todos'; }, 'secondary small'), button('场地审批', () => { location.hash = 'resources'; }, 'secondary small'), button('活动举报处理', () => { location.hash = 'reports'; }, 'secondary small'), button('查看社团统计', () => { location.hash = 'statistics'; }, 'secondary small')));
      result.append(el('div', { class: 'stats-grid' }, stat('待审核活动', pendingActivities.length, '社团提交的活动申请'), stat('待审核备案', pendingFilings.length, '新社团成立申请'), stat('校园社团', clubs.length, '查看状态与负责人'), stat('未读通知', state.unread, '管理动态及时掌握')),
        section('活动审核', pendingActivities.length), el('div', { class: 'panel' }, pendingActivities.length ? el('div', { class: 'list' }, pendingActivities.map(activityRow)) : empty('活动审核已处理完毕', '新提交的活动会出现在这里。')),
        section('社团备案审核', pendingFilings.length), el('div', { class: 'panel' }, pendingFilings.length ? el('div', { class: 'list' }, pendingFilings.map(f => row(f.name, `${f.applicant_name || '社团申请人'} · 申请成立社团`, [
          button('审核通过', event => perform(event.currentTarget, () => api(`/api/club-registrations/${f.id}/review`, 'POST', { decision: 'approve', reason: '' }), '备案审核通过，已建立正式社团'), 'small'),
          button('驳回', () => reviewDialog('社团备案', `/api/club-registrations/${f.id}/review`, 'reject'), 'danger small')], f.description))) : empty('暂无待审核备案', '社团申请人提交的备案资料将显示在这里。')),
        section('社团管理', clubs.length), el('div', { class: 'panel' }, clubs.length ? el('div', { class: 'list' }, clubs.map(c => row(c.name, `负责人：${c.leader_name || '尚未指定'}`, [badge(c.status), button('社团状态与负责人', () => governanceDialog(c), 'secondary small')]))) : empty('暂无社团记录')));
    } else {
      const [registrations, applications] = await Promise.all([api('/api/my/registrations'), api('/api/my/applications')]);
      result.append(el('div', { class: 'stats-grid' }, stat('我的社团', memberships().length, '当前加入的社团'), stat('有效报名', registrations.filter(r => ['confirmed', 'waitlisted'].includes(r.status)).length, '记得留意活动时间'), stat('待办任务', tasks.filter(t => t.status !== 'done').length, '尚未完成的筹备任务'), stat('未读通知', state.unread, '及时掌握最新进展')));
      if (leaderClubs().length) {
        result.append(section('我负责的社团'), el('div', { class: 'panel' }, el('div', { class: 'list' }, leaderClubs().map(c => row(c.club_name, '管理权限限于你负责的社团', [button('成员与申请', () => membershipDialog({ id: c.club_id, name: c.club_name }), 'secondary small'), button('创建活动', () => activityForm(null, c.club_id), 'small')])))),
          section('社团活动', activities.length), el('div', { class: 'panel' }, activities.length ? el('div', { class: 'list' }, activities.map(activityRow)) : empty('暂无社团活动', '创建草稿，完善活动安排，然后提交审核。', button('创建活动', () => activityForm(), 'small'))));
      } else {
        result.append(section('近期参与'), el('div', { class: 'panel' }, registrations.filter(r => r.status === 'confirmed').length ? el('div', { class: 'list' }, registrations.filter(r => r.status === 'confirmed').slice(0, 5).map(r => row(r.title, `${date(r.start_time)} · ${r.location}`, [badge(r.checked_in ? 'done' : r.status), button('活动详情', () => activityDetail(r.activity_id), 'ghost small')]))) : empty('暂无有效报名', '可前往活动广场查看并报名活动。', button('去活动广场', () => { location.hash = 'activities'; }, 'small'))),
          section('我的社团'), el('div', { class: 'panel' }, memberships().length ? el('div', { class: 'list' }, memberships().map(c => row(c.club_name, c.role === 'leader' ? '社团负责人' : '社团成员', [button('社团详情', () => clubDetail(c.club_id), 'ghost small')]))) : empty('尚未加入社团', applications.some(a => a.status === 'pending') ? '你有待审核的入社申请，可在“我的参与”跟进进度。' : '可查看社团介绍并提交入社申请。', button('发现社团', () => { location.hash = 'clubs'; }, 'small'))));
      }
      if (tasks.some(t => t.status !== 'done')) result.append(section('筹备协作'), el('div', { class: 'panel' }, el('div', { class: 'list' }, tasks.filter(t => t.status !== 'done').slice(0, 4).map(t => row(t.title, `${t.activity_title} · ${t.assignee_name} · ${date(t.due_time)}`, [badge(t.status), button('管理任务', () => { location.hash = 'tasks'; }, 'ghost small')])))));
    }
    return result;
  }
  function stat(label, count, hint) { return el('div', { class: 'stat-card' }, el('div', { class: 'label' }, label), el('strong', {}, count), el('div', { class: 'hint' }, hint)); }

  function statisticsChart(activities) {
    if (!activities.length) return null;
    const series = [
      { key: 'registration_count', label: '正式报名', tone: 'primary' },
      { key: 'check_in_count', label: '现场签到', tone: 'secondary' },
      { key: 'feedback_count', label: '活动评价', tone: 'tertiary' },
    ];
    const max = Math.max(1, ...activities.flatMap(activity => series.map(item => Number(activity[item.key]) || 0)));
    const chart = el('section', { class: 'panel statistics-chart', 'aria-label': '已结束活动参与数据对比' },
      el('h2', {}, '活动参与对比'),
      el('p', { class: 'tiny' }, '每组依次显示正式报名、签到和评价数量，数据与下方明细一致。'),
      el('div', { class: 'chart-legend' }, series.map(item => el('span', {}, el('i', { class: `chart-swatch ${item.tone}`, 'aria-hidden': 'true' }), item.label))));
    activities.forEach(activity => {
      const group = el('div', { class: 'chart-row' }, el('h3', { class: 'chart-title' }, activity.title));
      series.forEach(item => {
        const count = Number(activity[item.key]) || 0;
        const bar = el('div', { class: `chart-bar ${item.tone}`, 'aria-hidden': 'true' });
        bar.style.setProperty('--bar-size', `${count / max * 100}%`);
        if (!count) bar.classList.add('is-zero');
        group.append(el('div', { class: 'chart-series', role: 'img', 'aria-label': `${activity.title}，${item.label} ${count} 人` },
          el('span', { class: 'chart-series-label' }, item.label), el('div', { class: 'chart-track' }, bar), el('strong', { class: 'chart-value' }, count)));
      });
      chart.append(group);
    });
    return chart;
  }

  async function recordsView() {
    const [registrations, applications, filings, reports] = await Promise.all([api('/api/my/registrations'), api('/api/my/applications'), api('/api/club-registrations'), isStudent() ? api('/api/reports') : Promise.resolve([])]);
    const result = el('div', {}, heading('我的参与', '查看活动报名、入社申请、备案及举报记录。', isStudent() ? button('＋ 申请成立社团', () => filingDialog(), 'secondary small') : null));
    const tabs = [['registrations', '活动报名', registrations.length], ['applications', '入社申请', applications.length], ['filings', isStaff() ? '社团备案记录' : '社团备案申请', filings.length]];
    if (isStudent()) tabs.push(['reports', '举报记录', reports.length]);
    if (!tabs.some(t => t[0] === state.recordTab)) state.recordTab = 'registrations';
    result.append(el('div', { class: 'tabs', role: 'tablist', 'aria-label': '参与记录类型' }, tabs.map(([name, text, count]) => el('button', { class: `tab ${state.recordTab === name ? 'active' : ''}`, role: 'tab', type: 'button', 'aria-selected': state.recordTab === name ? 'true' : 'false', onclick: () => { state.recordTab = name; renderView(); } }, `${text} · ${count}`))));
    let content;
    if (state.recordTab === 'registrations') {
      content = registrations.length ? el('div', { class: 'list' }, registrations.map(r => row(r.title, `${date(r.start_time)} · ${r.location}`, [badge(r.status), r.checked_in ? badge('done') : null, button('活动详情', () => activityDetail(r.activity_id), 'ghost small')].filter(Boolean), r.status === 'waitlisted' ? '已加入候补。报名开放且未截止时，如有名额将按顺序转为正式报名。' : null))) : empty('暂无报名记录', '报名后可在这里查看状态和活动详情。');
    } else if (state.recordTab === 'applications') {
      content = applications.length ? el('div', { class: 'list' }, applications.map(a => row(a.club_name, `申请说明：${a.message || '无'}`, [badge(a.status), button('社团详情', () => clubDetail(a.club_id), 'ghost small'), a.status === 'pending' ? button('撤回申请', event => perform(event.currentTarget, () => api(`/api/applications/${a.id}/cancel`, 'POST', {}), '入社申请已撤回'), 'danger small') : null].filter(Boolean), a.reason ? `审核反馈：${a.reason}` : null))) : empty('还没有入社申请', '先了解喜欢的社团，再提交一份简单的自我介绍。');
    } else if (state.recordTab === 'reports') {
      content = reports.length ? el('div', { class: 'list' }, reports.map(r => row(r.activity_title, '你提交的活动举报', [badge(r.status)], `举报原因：${r.reason}${r.resolution ? `\n处理结果：${r.resolution}` : ''}`))) : empty('暂时没有举报记录', '如发现活动存在问题，可在活动详情中向管理中心反映。');
    } else {
      content = filings.length ? el('div', { class: 'list' }, filings.map(f => row(f.name, f.applicant_name ? `申请人：${f.applicant_name}` : '社团成立备案', [badge(f.status)], `${f.description}${f.reason ? `\n审核反馈：${f.reason}` : ''}`))) : empty('还没有社团备案申请', '如果你想组织一个新的兴趣社团，可以从备案申请开始。');
    }
    result.append(el('div', { class: 'panel', role: 'tabpanel' }, content));
    return result;
  }
  async function todosView() {
    const todos = await api('/api/todos');
    const names = { task: '筹备任务', application: '入社申请', activity: '活动审核', club_registration: '社团备案', venue_application: '场地审核', report: '活动举报' };
    const open = todo => {
      if (todo.kind === 'task') location.hash = 'tasks';
      else if (todo.kind === 'activity') activityDetail(todo.activity_id || todo.id);
      else if (todo.kind === 'application') { const c = memberships().find(m => Number(m.club_id) === Number(todo.club_id)); membershipDialog({ id: todo.club_id, name: c?.club_name || '社团入社申请' }); }
      else if (todo.kind === 'venue_application') location.hash = 'resources';
      else if (todo.kind === 'report') location.hash = 'reports';
      else location.hash = 'dashboard';
    };
    return el('div', {}, heading('待办事项', '汇总你能处理的任务、申请与审核，只保留尚未完成的事项。'),
      todos.length ? el('div', { class: 'panel' }, el('div', { class: 'list' }, todos.map(t => row(t.title, `${names[t.kind] || '业务事项'} · ${t.deadline ? `截止：${date(t.deadline)}` : '暂无固定期限'}`, [button('前往处理', () => open(t), 'small')])))) : empty('待办已清空', '当前没有待处理的任务、申请或审核。'));
  }
  async function resourcesView() {
    const [applications, venues] = await Promise.all([api('/api/venue-applications'), api('/api/venues')]);
    const staff = isStaff();
    return el('div', {}, heading(staff ? '场地资源与审批' : '社团活动资源', staff ? '核对活动使用时间，协调校园场地，避免资源冲突。' : '为活动申请合适的场地，跟进审批与物资筹备。', !staff ? button('＋ 申请活动场地', () => venueForm()) : null),
      el('div', { class: 'panel' }, el('h2', {}, '校园场地'), venues.length ? el('div', { class: 'venue-grid' }, venues.map(v => el('div', { class: 'venue-card' }, el('span', { class: 'venue-symbol', 'aria-hidden': 'true' }, '⌖'), el('div', {}, el('h3', {}, v.name), el('p', {}, v.description))))) : el('p', {}, '暂无场地记录。')),
      section(staff ? '场地使用申请' : '我负责社团的场地申请', applications.length), el('div', { class: 'panel' }, applications.length ? el('div', { class: 'list' }, applications.map(a => row(a.activity_title, `${a.venue_name} · ${date(a.start_time)} — ${date(a.end_time)}`, [badge(a.status), button('活动详情', () => activityDetail(a.activity_id), 'ghost small'), ...(staff && a.status === 'pending' ? [
        button('批准场地申请', event => perform(event.currentTarget, () => api(`/api/venue-applications/${a.id}/review`, 'POST', { decision: 'approve', reason: '' }), '场地申请已批准'), 'small'),
        button('驳回', () => reviewDialog('场地申请', `/api/venue-applications/${a.id}/review`, 'reject'), 'danger small')] : [])], a.reason ? `审批说明：${a.reason}` : null))) : empty('暂无场地申请', staff ? '社团提交的场地使用申请将显示在这里。' : '活动提交审核后，可在详情中申请场地。物资筹备也可从活动详情进入。')));
  }
  async function statisticsView() {
    const clubs = isStaff() ? await api('/api/clubs') : leaderClubs().map(m => ({ id: m.club_id, name: m.club_name }));
    if (!clubs.length) return el('div', {}, heading('社团参与统计', '查看已结束及归档活动的参与情况。'), empty('暂无可查看的社团', '只有所属社团负责人和管理中心工作人员可以查看社团统计。'));
    if (!clubs.some(c => String(c.id) === String(state.statisticsClub))) state.statisticsClub = String(clubs[0].id);
    const data = await api(`/api/clubs/${state.statisticsClub}/statistics`);
    const select = el('select', { name: 'statistics_club', 'aria-label': '统计社团', onchange: event => { state.statisticsClub = event.currentTarget.value; renderView(); } }, clubs.map(c => el('option', { value: c.id }, c.name)));
    select.value = state.statisticsClub;
    const list = data.activities || [];
    const count = key => list.reduce((sum, a) => sum + Number(a[key] || 0), 0);
    const csv = el('a', { class: 'btn secondary small', href: `/api/clubs/${state.statisticsClub}/statistics.csv`, download: `${data.club_name || '社团'}-活动统计.csv` }, '下载统计 CSV');
    const table = el('table', {}, el('thead', {}, el('tr', {}, ['活动', '状态', '正式报名', '现场签到', '活动评价'].map(t => el('th', { scope: 'col' }, t)))), el('tbody', {}, list.map(a => el('tr', {}, el('td', {}, el('button', { type: 'button', class: 'inline-link', onclick: () => activityDetail(a.id) }, a.title)), el('td', {}, badge(a.status)), el('td', {}, a.registration_count), el('td', {}, a.check_in_count), el('td', {}, a.feedback_count)))));
    return el('div', {}, heading('社团参与统计', '查看已结束和已归档活动的报名、签到与评价数量。', csv), el('div', { class: 'toolbar statistics-toolbar' }, select, el('span', { class: 'count-label' }, '统计仅包含已结束与已归档活动，不包含候补和已取消报名。')),
      el('div', { class: 'stats-grid' }, stat('已完成活动', list.length, data.club_name), stat('正式报名', count('registration_count'), '已占用正式名额的报名'), stat('现场签到', count('check_in_count'), '已登记到场参与'), stat('活动评价', count('feedback_count'), '来自已签到参与者')),
      statisticsChart(list),
      el('div', { class: 'panel' }, list.length ? el('div', { class: 'table-wrap' }, table) : empty('暂无活动统计', '目前这个社团还没有已结束或归档的活动。')));
  }
  async function reportsView() {
    const reports = await api('/api/reports');
    const pending = reports.filter(r => r.status === 'pending');
    return el('div', {}, heading('活动举报处理', '核查学生反映的问题，记录处理情况并保留管理过程。'),
      section('待处理举报', pending.length), el('div', { class: 'panel' }, pending.length ? el('div', { class: 'list' }, pending.map(r => row(r.activity_title, '学生提交的活动问题', [button('查看活动', () => activityDetail(r.activity_id), 'ghost small'), button('记录处理结果', () => resolveReportDialog(r), 'small')], r.reason))) : empty('待处理举报已清空', '新的学生举报会显示在这里。')),
      section('已处理记录', reports.length - pending.length), el('div', { class: 'panel' }, reports.some(r => r.status === 'resolved') ? el('div', { class: 'list' }, reports.filter(r => r.status === 'resolved').map(r => row(r.activity_title, '管理中心已处理', [badge(r.status)], `举报原因：${r.reason}\n处理结果：${r.resolution}`))) : empty('暂无已处理记录')));
  }
  async function tasksView() {
    const tasks = await api('/api/tasks');
    const result = el('div', {}, heading('筹备任务', '查看任务负责人、截止时间和当前进度。'));
    if (!tasks.length) { result.append(empty('暂时没有筹备任务', leaderClubs().length ? '在工作台打开活动详情，为本社团成员安排任务。' : '被分配的社团筹备任务会显示在这里。')); return result; }
    result.append(el('div', { class: 'task-board' }, ['todo', 'in_progress', 'done'].map(status => {
      const items = tasks.filter(t => t.status === status);
      return el('section', { class: 'task-column', 'aria-label': statusLabels[status] }, el('h2', {}, statusLabels[status], el('span', {}, items.length)), items.map(t => {
        const allowed = t.status === 'todo' ? ['todo', 'in_progress'] : t.status === 'in_progress' ? ['in_progress', 'done'] : ['done'];
        const select = el('select', { 'aria-label': `${t.title}的任务状态`, disabled: t.status === 'done', onchange: event => {
          const control = event.currentTarget;
          perform(control, () => api(`/api/tasks/${t.id}`, 'PATCH', { status: control.value }), '任务进度已更新').then(ok => { if (!ok) control.value = t.status; });
        } }, allowed.map(s => el('option', { value: s }, statusLabels[s])));
        select.value = t.status;
        const overdue = status !== 'done' && new Date(t.due_time) < new Date();
        return el('article', { class: 'task-card' }, el('h3', {}, t.title), el('p', {}, t.activity_title), el('p', {}, `负责人：${t.assignee_name}`), el('p', { class: overdue ? 'overdue' : '' }, `截止：${date(t.due_time)}${overdue ? ' · 已逾期' : ''}`), select);
      }), items.length ? null : el('p', { class: 'text-muted tiny' }, '这个阶段暂无任务。'));
    })));
    return result;
  }
  async function notificationsView() {
    const notices = await api('/api/notifications');
    return el('div', {}, heading('站内通知', '查看审核结果、报名变化及任务通知。'),
      notices.length ? el('div', { class: 'panel' }, notices.map(n => el('article', { class: 'notice-item' }, el('span', { class: `notice-dot ${n.read ? 'read' : ''}`, 'aria-label': n.read ? '已读' : '未读' }), el('div', { class: 'notice-body' }, el('h3', {}, n.title), el('p', {}, n.message), el('time', { datetime: n.created_at }, date(n.created_at))), n.read ? null : button('标为已读', event => perform(event.currentTarget, () => api(`/api/notifications/${n.id}/read`, 'POST', {}), ''), 'ghost small')))) : empty('暂时没有新消息', '有新的申请结果或活动、任务通知时，将显示在这里。'));
  }
  async function auditView() {
    const [audit, logs] = await Promise.all([api('/api/audit'), api('/api/logs')]);
    const actionNames = {
      demo_initialized: '初始化课程演示资料', lifecycle_advance: '更新活动状态',
      club_profile_imported: '录入社团资料', account_password_set: '设置账号密码',
      application_created: '提交入社申请', application_approved: '通过入社申请',
      application_rejected: '驳回入社申请', application_cancelled: '撤回入社申请',
      membership_changed: '调整社团成员状态', club_registration_created: '提交社团备案',
      club_registration_approved: '通过社团备案', club_registration_rejected: '驳回社团备案',
      club_status_changed: '调整社团状态', club_leader_changed: '确认负责人变更',
      activity_created: '创建活动草稿', activity_edited: '修改活动草稿',
      activity_submit: '提交活动审核', activity_approve: '审核通过活动',
      activity_reject: '驳回活动', activity_publish: '发布活动',
      activity_open_registration: '开放活动报名', activity_cancel: '取消活动',
      activity_archive: '归档活动', registration_confirmed: '正式报名活动',
      registration_waitlisted: '加入活动候补', registration_cancelled: '取消活动报名',
      waitlist_promoted: '候补转为正式报名', check_in_recorded: '登记现场签到',
      task_created: '创建筹备任务', task_status_changed: '更新筹备任务进度',
      venue_application_created: '提交场地申请', venue_application_approved: '批准场地申请',
      venue_application_rejected: '驳回场地申请', material_requested: '登记物资需求',
      material_status_changed: '更新物资准备进度', feedback_created: '提交活动评价',
      report_created: '提交活动举报', report_resolved: '处理活动举报',
    };
    const entityNames = { activity: '活动', club: '社团', club_registration: '社团备案', registration: '活动报名', application: '入社申请', task: '筹备任务', membership: '成员关系', user: '用户', system: '系统', venue_application: '场地申请', material: '活动物资', feedback: '活动评价', report: '活动举报' };
    const table = el('table', {}, el('thead', {}, el('tr', {}, ['时间', '操作人', '业务操作', '业务对象'].map(t => el('th', { scope: 'col' }, t)))), el('tbody', {}, audit.map(a => el('tr', {}, el('td', {}, date(a.created_at)), el('td', {}, a.actor_name || '系统'), el('td', {}, actionNames[a.action] || '业务操作'), el('td', {}, `${entityNames[a.entity_type] || '业务记录'} ${a.entity_id || ''}`)))));
    return el('div', {}, heading('管理记录', '查看社团审核、活动状态和成员身份的变更记录。'), section('操作记录', audit.length), el('div', { class: 'panel' }, audit.length ? el('div', { class: 'table-wrap' }, table) : empty('暂无操作记录')),
      section('运行情况', logs.length), el('div', { class: 'panel' }, logs.length ? el('div', { class: 'list' }, logs.map(l => row(l.message || l.action || '运行记录', `${date(l.created_at)}${l.level ? ` · ${l.level}` : ''}`))) : empty('暂无运行日志', '系统运行记录将在这里显示。')));
  }

  async function renderView() {
    const generation = ++state.generation;
    const requested = location.hash.slice(1).split('?')[0] || 'activities';
    state.view = labels[requested] ? requested : 'activities';
    if (!state.user && !['activities', 'clubs', 'calendar'].includes(state.view)) state.view = 'activities';
    if (['audit', 'reports'].includes(state.view) && !isStaff()) state.view = 'dashboard';
    if (['resources', 'statistics'].includes(state.view) && !isStaff() && !leaderClubs().length) state.view = 'dashboard';
    if (state.view === 'recommendations' && !isStudent()) state.view = 'activities';
    renderNavigation(); document.getElementById('page-label').textContent = labels[state.view];
    document.title = `${labels[state.view]} · 青禾校园社团`;
    main.setAttribute('aria-busy', 'true'); main.replaceChildren(el('div', { class: 'loading-state', role: 'status' }, '正在加载页面…'));
    const renderers = { activities: activitiesView, clubs: clubsView, calendar: calendarView, recommendations: recommendationsView, dashboard: dashboardView, todos: todosView, records: recordsView, tasks: tasksView, resources: resourcesView, statistics: statisticsView, reports: reportsView, notifications: notificationsView, audit: auditView };
    try {
      const content = await renderers[state.view]();
      if (generation === state.generation) main.replaceChildren(content);
    } catch (error) {
      if (generation === state.generation) main.replaceChildren(heading('暂时无法加载页面', '请稍后再试。'), el('div', { class: 'error-box' }, error.message), el('div', { class: 'action-row action-gap' }, button('重新加载', () => renderView(), 'secondary')));
    } finally { if (generation === state.generation) main.removeAttribute('aria-busy'); }
  }
  window.addEventListener('hashchange', () => { renderView(); });
  async function start() {
    try { await session(); await renderView(); }
    catch (error) { main.replaceChildren(heading('暂时无法连接服务', '请检查网络连接，稍后重试。'), el('div', { class: 'error-box' }, error.message), el('div', { class: 'action-row action-gap' }, button('重新连接', () => start(), 'secondary'))); }
  }
  function syncStatusAccent() {
    // Keep yellow and blue as the two structural colors; use one semantic color at a time.
    const hasError = document.querySelector('.status-badge.red, .toast.error, .error-box:not(:empty)');
    const hasSuccess = document.querySelector('.status-badge.green');
    const accent = hasError ? 'red' : hasSuccess ? 'green' : 'none';
    if (document.body.dataset.statusAccent !== accent) document.body.dataset.statusAccent = accent;
  }
  new MutationObserver(syncStatusAccent).observe(document.body, { childList: true, subtree: true });
  syncStatusAccent();
  start();
})();
