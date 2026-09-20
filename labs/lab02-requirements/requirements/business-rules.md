# 业务规则

| ID | 规则 | 来源 |
|---|---|---|
| BR-001 | 仅 Published 或 RegistrationOpen 且未超过报名截止时间的活动允许正式报名；截止时刻按服务器统一时间判定。 | Q04, DOMAIN |
| BR-002 | 同用户同活动最多一条有效正式报名；容量是正式报名上限，并发提交不得超额。 | Q04, Q06, DOMAIN |
| BR-003 | 满员时默认返回“已满”；若后续启用候补，按入列顺序保留候补，不把候补计入正式容量。 | Q06 |
| BR-004 | 正式报名者在活动开始前可取消；取消释放的名额先给第一位有效候补，转正、容量更新及通知须一致完成；无候补才开放新报名。 | Q05, Q06, INT-ORGANIZER |
| BR-005 | 候补者取消后不再被自动转正；活动报名关闭后不再转正。 | Q06, DOMAIN |
| BR-006 | 活动主状态：Draft→Submitted→Approved→Published→RegistrationOpen→RegistrationClosed→InProgress→Finished→Archived；Rejected 可从 Submitted 进入，修改后可重新提交；Cancelled 可从 Published 至 InProgress 前的适用状态进入。状态推进须记录操作者及时间。 | INT-ADMIN, INT-ORGANIZER |
| BR-007 | 报名开放与关闭可以由截止时间触发；Published 不等于 RegistrationOpen。取消活动后停止新报名与签到，并通知已报名者。 | INT-STUDENT, DOMAIN |
| BR-008 | 筹备任务至少有标题、负责人、状态、截止时间和所属活动。状态为待办、进行中、完成；非完成任务逾期可标记提醒，但不自动改为完成。 | Q11, Q12, INT-ORGANIZER |
| BR-009 | 每次敏感操作同时核对 Role 与 Resource Ownership。社团负责人只管理所属社团资源；平台管理员的审核权限按职责独立授予。 | INT-ADMIN, DOMAIN |
| BR-010 | 签到仅面向正式报名者，在活动 InProgress 时确认；同人同活动不能重复有效签到。 | Q08, INT-ORGANIZER |
| BR-011 | 活动审核驳回必须给原因；未经 Approved 不得发布。 | INT-ADMIN |
| BR-012 | 场地申请获批前，若同场地时间段存在重叠的已批准申请，则拒绝批准。 | Q13, INT-ADMIN |

上述是需求层的状态和一致性规则，未规定数据库表、锁实现或界面设计。具体取消时限、提醒提前量与时间区间边界在设计前与教师确认。
