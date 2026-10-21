# 校园社团活动管理系统

暨南大学《软件工程实验》课程设计。项目面向校园社团活动的筹备、审核、发布、报名、签到与协作，目标是让活动信息、办理状态和任务责任更清楚。

产品定位：面向学校社团管理中心、学生社团和普通学生的校园社团综合管理与协同平台。

## 当前进度

- 实验 1：环境搭建、Hello World、选题及初步计划。
- 实验2：真实问卷369份经填写者确认修订后纳入[正式统计](labs/lab02-requirements/research/questionnaire-results.md)，需求依据更新为`requirements-v1.2`；真实访谈尚未完成。

需求分析版本已保留，开发在 `feat/core-platform` 分支推进。当前课程演示版本已实现登录、社团治理和成员管理、活动审核发布、报名候补与签到、任务通知、待办日历、资源申请、评价统计、推荐举报和导出，并提供审计及备份恢复。业务和浏览器验证记录见 [验证结果](docs/design/verification.md)。

## 运行系统

Windows 在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

首次使用其他电脑时，需要先安装 Python 依赖并初始化演示数据。完整步骤、演示账号及操作顺序见 [本地运行说明](project/README.md)。服务默认地址为 http://127.0.0.1:5000。

## 仓库结构

- `docs/`：项目概述、候选范围和术语。
- `labs/lab01-environment/`：实验 1 报告与运行证据。
- `labs/lab02-requirements/`：实验 2 调研、需求与 SRS。
- `docs/project-management/`：后续开发的项目计划、产品待办、迭代计划、风险与变更记录。
- `docs/design/`：软件设计及接口约定。
- `project/src/`：后端和浏览器界面；`project/tests/`：业务与浏览器验证。
