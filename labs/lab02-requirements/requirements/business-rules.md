# 业务规则

| ID | 规则 | 来源 |
|---|---|---|
| BR-001 | 只有处于 RegistrationOpen 状态且当前时间早于报名截止时间的活动允许正式报名；Published 只表示活动公开可见。到达报名截止时刻即不再接受报名，截止时刻按系统统一时间判定。 | Q04, 领域约束 |
| BR-002 | 同用户同活动最多一条有效正式报名；容量是正式报名上限，并发提交不得超额。 | Q04, Q06, 领域约束 |
| BR-003 | 满员时默认返回“已满”；若后续启用候补，按入列顺序保留候补，不把候补计入正式容量。 | Q06 |
| BR-004 | 正式报名者可在报名截止时间前自行取消；超过报名截止时间后不得自行取消。取消释放的名额先给第一位有效候补，转正、容量更新及通知应保持一致；无有效候补时名额重新开放。 | Q05, Q06, INT-ORGANIZER |
| BR-005 | 候补者取消后不再被自动转正；达到报名截止时间或活动进入 RegistrationClosed 后不再自动转正。 | Q06, 领域约束 |
| BR-006 | Draft 在负责人创建活动时进入；资料完整后提交进入 Submitted；学校社团管理中心工作人员通过后进入 Approved，驳回则进入 Rejected；Rejected 修改后回到 Draft。负责人将 Approved 活动发布后进入 Published，并可在报名截止时间前开启报名进入 RegistrationOpen；Published 或 RegistrationOpen 到达报名截止时间后进入 RegistrationClosed；到达活动开始时间后进入 InProgress；活动结束后进入 Finished；完成资料归档后进入 Archived。Published、RegistrationOpen 或 RegistrationClosed 可在活动开始前进入 Cancelled。所有状态变化均记录操作者和时间。 | INT-ADMIN, INT-ORGANIZER, 领域约束 |
| BR-007 | Published 不等于 RegistrationOpen。开启报名由所属社团负责人在活动已发布且报名截止时间未到达时执行；报名截止时间到达后系统关闭报名。活动取消后停止报名、候补转正和签到，并通知已有正式报名者及有效候补者。 | INT-STUDENT, 领域约束 |
| BR-008 | 筹备任务至少有标题、负责人、状态、截止时间和所属活动。状态为待办、进行中、完成；非完成任务逾期可标记提醒，但不自动改为完成。 | Q11, Q12, INT-ORGANIZER |
| BR-009 | 每次敏感操作同时核对 Role Permission 与 Resource Ownership。普通学生只管理本人的入社申请、报名、签到、评价和个人记录；社团负责人只管理自己负责社团的成员、活动、任务和资源申请；学校社团管理中心工作人员按职责拥有跨社团审核、治理、资源审批、统计和审计权限。 | INT-ADMIN, 领域约束 |
| BR-010 | 签到仅面向正式报名者，在活动 InProgress 时确认；同人同活动不能重复有效签到。 | Q08, INT-ORGANIZER |
| BR-011 | 活动审核驳回必须给原因；未经 Approved 不得发布。 | INT-ADMIN |
| BR-012 | 场地申请获批前，若同场地时间段存在重叠的已批准申请，则拒绝批准。 | Q13, INT-ADMIN |

上述是需求层的状态和一致性规则，未规定数据库表、锁实现或界面设计。提醒提前量与时间区间的精确边界在设计前确认；取消报名统一以报名截止时间为边界。
