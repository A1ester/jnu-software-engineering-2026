# 核心版本接口约定

设计日期：2026-10-13。以 requirements-v1.1 为需求输入；首版实现身份、社团治理和成员、活动、报名签到、筹备任务及站内通知。技术方案为 Flask、SQLite 和原生 Web 页面。接口与界面同源，JSON 成功响应统一为 `{ "data": ... }`，失败为 `{ "error": { "code": "...", "message": "中文说明" } }`。列表的 data 是数组，详情的 data 是对象。

## 会话及输入

- `GET /api/session` → `{user: null|User, csrf_token: string}`。User：`id, username, display_name, role`（student/staff）, `memberships: [{club_id, club_name, role: member|leader, active: boolean}]`。
- `POST /api/login`：`username,password` → 与 session 相同。`POST /api/logout` → `{ok:true}`。
- 所有 POST/PATCH/DELETE 包括登录都携带 session 返回的 `X-CSRF-Token`；HttpOnly 同源会话 cookie；服务端检查权限和资源归属。
- 时间输入采用带时区 ISO 8601（前端将 datetime-local 转换为 ISO）；以 UTC 保存和判定，界面显示本机时间。
- 文本长度、容量和枚举在服务端校验；非授权读操作返回 403，隐藏的活动对访客返回 404。重复报名、非法业务状态等返回 409。
- 测试工厂 `campus_clubs.create_app(config)`，config 支持 `TESTING, DATABASE, SECRET_KEY, NOW`（返回 aware datetime 的函数），业务时间从 NOW 获取。

## 资源

| 接口 | 数据及业务 |
|---|---|
| GET /api/clubs | Club 数组：id,name,description,status,leader_name；不返回成员资料 |
| GET /api/clubs/:id | Club，公开信息 |
| GET /api/my/clubs | 本人社团，包括成员身份和状态 |
| POST /api/clubs/:id/applications | `{message}` 入社申请 |
| GET /api/my/applications | 本人申请：id,club_id,club_name,message,status |
| POST /api/applications/:id/cancel | 本人撤回待处理申请，其他状态拒绝 |
| GET /api/clubs/:id/applications | 仅所属负责人；包含申请学生显示名 |
| POST /api/applications/:id/review | `{decision: approve|reject,reason}`，所属负责人 |
| GET /api/clubs/:id/members | 所属负责人或管理中心工作人员；id（成员关系）,user_id,display_name,role,active；供成员管理和负责人变更选择 |
| PATCH /api/clubs/:id/members/:id | `{active: boolean}`，所属负责人；不能停用现任负责人 |
| POST /api/club-registrations | `{name,description}`，学生申请人 |
| GET /api/club-registrations | 本人备案，staff 可查看全部；id,name,description,applicant_name,status,reason |
| POST /api/club-registrations/:id/review | `{decision,reason}`，staff；通过后形成社团及负责人关系 |
| PATCH /api/clubs/:id/governance | `{status: active|disabled}` 或 `{leader_id: user_id}`，staff；负责人变更须是有效成员并留痕 |
| GET /api/activities | 公开活动，可选 q,theme,club_id,date（开始日 YYYY-MM-DD）,utc_offset（相对 UTC 的分钟偏移，-840～840，默认 0）；日期按给定偏移的本地日区间筛选；Activity 数组 |
| GET /api/my/activities | 所属负责人所有活动（含草稿），staff 所有待审核活动 |
| GET /api/activities/:id | Activity，含本人 my_registration:null|{id,status,checked_in}；所属负责人可见非公开详情 |
| POST /api/activities | `{club_id,title,theme,description,location,capacity,registration_deadline,start_time,end_time,waitlist_enabled}` → Activity |
| PATCH /api/activities/:id | 同上可编辑字段；仅所属负责人 Draft/Rejected，Rejected 编辑后回 Draft |
| POST /api/activities/:id/transition | `{action: submit|approve|reject|publish|open_registration|cancel|archive,reason}`，审核 action 仅 staff，其余仅所属负责人 |
| POST /api/activities/:id/registrations | 无正文，正式或候补（confirmed/waitlisted） |
| GET /api/my/registrations | 本人报名：id,activity_id,title,status,checked_in,start_time,location |
| POST /api/registrations/:id/cancel | 本人取消，严格早于截止；候补者可取消候补 |
| GET /api/activities/:id/registrations | 所属负责人，或 InProgress 时有效所属成员用于签到；报名 id,user_id,display_name,status,checked_in；不返回联系方式 |
| POST /api/activities/:id/check-ins | `{user_id}`；所属负责人或有效所属成员，活动 InProgress 且正式报名；重复拒绝 |
| GET /api/tasks | 本人被分配任务、负责社团所有任务；id,activity_id,activity_title,title,assignee_id,assignee_name,due_time,status（todo/in_progress/done） |
| POST /api/activities/:id/tasks | `{title,assignee_id,due_time}`；所属负责人；任务担当人是有效所属成员 |
| PATCH /api/tasks/:id | `{status}`；本人任务担当人或所属负责人；todo → in_progress → done，完成后不可退回，同状态重复请求不生成重复通知 |
| GET /api/notifications | 本人 id,title,message,read,created_at |
| POST /api/notifications/:id/read | 本人读通知，幂等 |
| GET /api/audit | staff 查看审计记录，id,actor_name,action,entity_type,entity_id,created_at |
| GET /api/logs | staff 查看运行日志（不含账号密码和会话信息） |

Activity：`id,club_id,club_name,title,theme,description,location,capacity,registration_deadline,start_time,end_time,waitlist_enabled,status,registered_count,waitlist_count`。状态严格保持 SRS 的 Draft / Submitted / Approved / Rejected / Published / RegistrationOpen / RegistrationClosed / InProgress / Finished / Archived / Cancelled。后台或请求中的生命周期刷新只对已发布活动推进；Cancelled 不再推进。

报名、取消与候补转正使用同一写事务，约束同用户同活动的有效记录唯一性。通知与对应业务写入同一事务，避免重试产生重复通知。社团停用阻止其成员的社团业务写操作，同时保留历史记录和个人取消权。

## 本地启动与演示

入口 `python project/run.py init-demo` / `python project/run.py serve --port 5000`。所有运行数据位于忽略的 `project/instance/`。演示用户 `student`, `leader`, `member`, `other_leader`, `staff`，公开演示口令统一为 `Demo12345!`，仅 init-demo 创建；学生显示名采用演示标识。演示社团 1 为校园摄影社，社团 2 为读书社。至少提供一个开放报名活动、一个进行中活动和一个待审核活动，以便验证三类用户流程。

`init-demo` 对非空数据库应拒绝覆盖；备份用 SQLite backup API；恢复默认写到指定独立数据库，拒绝覆盖已有目标。记录课程演示限制，不把 Flask 内置服务器或演示账号作为生产部署。

## 第二轮：资源、反馈及统计

以下仍属于 requirements-v1.1 已有范围，不新增需求编号。权限、JSON 格式及事务规则沿用上述约定。

| 接口 | 数据及业务 |
|---|---|
| GET /api/todos | 本人可处理且未完成事项：kind（task/application/activity/club_registration/venue_application/report）,id,title,deadline,activity_id（可选）,club_id（可选）；任务、本人负责社团待处理入社申请、管理中心待审核活动/备案/场地/举报 |
| GET /api/venues | 场地 id,name,description；课程演示数据包含学生活动中心、图书馆交流室 |
| GET /api/venue-applications | staff 全部，leader 仅本人负责社团：id,activity_id,activity_title,venue_id,venue_name,start_time,end_time,status,reason |
| POST /api/activities/:id/venue-applications | `{venue_id,start_time,end_time}`；所属负责人，活动至少 Submitted 且未结束或取消，时间合法且落在活动开始/结束区间内 |
| POST /api/venue-applications/:id/review | `{decision,reason}`；staff，批准前在写事务中拒绝同场地重叠的已批准时段，区间为半开 [开始,结束)，相邻时段允许 |
| GET /api/activities/:id/materials | 所属负责人或 staff：id,name,quantity,status（requested/preparing/ready） |
| POST /api/activities/:id/materials | `{name,quantity}`；所属负责人 |
| PATCH /api/materials/:id | `{status}`；所属负责人，记录本人社团物资处理状态 |
| POST /api/activities/:id/feedback | `{rating:1..5,comment}`；本人已签到且活动 Finished/Archived，每人每活动一次 |
| GET /api/clubs/:id/statistics | 所属负责人或 staff；club_id,club_name,activities:[{id,title,status,registration_count,check_in_count,feedback_count}]；汇总已结束和归档活动 |
| GET /api/clubs/:id/statistics.csv | 与统计 JSON 相同数据的 CSV；不含账号、名单或联系方式；标题防止电子表格公式执行 |
| GET /api/recommendations | 已登录学生；可选 themes（逗号分隔主题）；返回公开 Activity，额外 recommendation_reason；主题匹配优先，其次开始时间，再以 id 稳定排序；无偏好仅按开始时间/id |
| POST /api/activities/:id/reports | `{reason}`；学生对公开活动举报，相同用户/活动/原因重复拒绝 |
| GET /api/reports | 学生仅本人，staff 全部：id,activity_id,activity_title,reason,status（pending/resolved）,resolution |
| POST /api/reports/:id/resolve | `{resolution}`；staff处理举报，记录处理结果和审计 |

日历界面按活动开始日分组，使用活动公开列表和本地日期显示；无需重复维护另一份活动数据。任务看板继续使用相同任务状态。已有核心流程的 44 项业务测试及 16 项浏览器检查已通过，第二轮另行验证。

活动详情附带本人评价 `my_feedback:null|{rating,comment}`，仅本人可见，不返回其他学生的评价内容。
