# 风险登记

| ID | Risk | Probability | Impact | Response | Status |
|---|---|---|---|---|---|
| RISK-001 | 项目范围过大，34 个功能需求超出个人课程周期 | High | High | 以 Must 为主线；Should/Could 只在核心闭环稳定且经评审后选取 | OPEN |
| RISK-002 | 需求依据课程练习中的构造问卷结果和典型角色场景，与真实校园流程可能存在偏差 | High | High | 保留真实性说明；设计前核对关键假设；真实部署前开展真实调研 | OPEN |
| RISK-003 | 课程时间不足导致设计、实现或测试压缩 | Medium | High | 按迭代设置完成判据；优先交付可验证增量；提前记录未完成范围 | OPEN |
| RISK-004 | 学校身份、场地或消息接口不可用 | High | Medium | 当前不承诺外部集成；以明确接口边界和站内能力完成课程版本 | OPEN |
| RISK-005 | Should/Could 功能挤压核心功能的实现和测试时间 | Medium | High | Iteration 4 才评估扩展项；核心 Must 未达成时不扩大范围 | OPEN |
| RISK-006 | 后续技术选型存在学习成本，估计偏差较大 | Medium | Medium | 设计阶段进行小规模技术验证；根据实际结果调整 Backlog 估计，不编造 Velocity | OPEN |
| RISK-007 | 需求状态、文档和实现之间出现不一致 | Medium | High | 使用稳定 ID、CR 记录和追踪矩阵；每个条目完成时同步更新相关文档 | OPEN |
| RISK-008 | Public 仓库意外包含个人邮箱、凭据或真实个人数据 | Low | High | 提交前检查差异和敏感信息；课程练习数据使用匿名标识；环境文档只写“已配置” | MONITORED |
