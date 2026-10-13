# 本地运行

校园社团活动管理系统核心版本，使用 Python 3.12 及以上、Flask 和 SQLite。本页命令从仓库根目录执行。

## Windows 首次安装

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r project/requirements.txt
.\.venv\Scripts\python.exe project/run.py init-demo
.\.venv\Scripts\python.exe project/run.py serve --port 5000
```

打开 http://127.0.0.1:5000。以后可以用 `powershell -ExecutionPolicy Bypass -File .\start.ps1` 启动；执行策略覆盖只作用于这次启动，不修改全局设置。停止服务按 Ctrl+C。

其他系统：`python3 -m venv .venv`，随后用 `.venv/bin/python` 执行同样的安装、初始化和启动命令。

## 演示账号

| 账号 | 身份与用途 |
|---|---|
| student | 普通学生：活动报名、入社申请、本人记录及社团备案申请 |
| leader | 摄影社负责人：成员、活动、报名签到及筹备管理 |
| member | 摄影社成员：本人筹备任务及授权签到 |
| other_leader | 读书社负责人：用于核对跨社团权限边界 |
| staff | 学校社团管理中心工作人员：活动与备案审核、社团治理、审计和日志 |

演示口令均为 `Demo12345!`。账号和业务数据仅用于课程演示，不对应真实学生或工作人员。只有明确执行 init-demo 才会创建这些账号；非空数据库拒绝重复初始化，已有记录不会被覆盖。

## 建议演示顺序

1. 访客查看社团及公开活动，使用主题、社团和日期筛选。
2. student 登录，申请加入摄影社并报名“校园摄影漫步”，查看本人状态及通知。
3. leader 处理入社申请、创建活动、分配筹备任务，再提交活动审核。
4. staff 审核活动；leader 发布并单独开启报名。
5. member 更新自己的任务，并在“摄影交流实践”中完成正式报名者签到。
6. student 提交新社团备案；staff 审核，通过后申请人成为新社团负责人。
7. leader 提交活动场地申请并登记物资；staff 审批场地；在活动结束后由已签到学生评价，负责人查看汇总统计或下载 CSV。
8. 学生在兴趣推荐中选择主题、查看日历与待办、反馈活动问题；管理中心在举报处理页记录处理结果。

报名截止时间到达后不再接受报名或转正；当前时间到达开始和结束时间时，已发布活动自动进入相应状态。系统统一使用 UTC 判断，页面按本机时间显示。

## 测试、备份及恢复

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s project/tests -v
.\.venv\Scripts\python.exe project/run.py tick
New-Item -ItemType Directory -Force project/backups | Out-Null
.\.venv\Scripts\python.exe project/run.py backup project/backups/before-demo.sqlite3
.\.venv\Scripts\python.exe project/run.py restore project/backups/before-demo.sqlite3 project/instance/restored.sqlite3
```

备份目标和恢复目标必须是不存在的新文件。恢复写到独立目标，不能覆盖正在运行的数据库。命令支持指定独立数据库进行验证，详见 `python project/run.py --help`。数据库、备份和本地会话属于运行数据，已从版本管理排除。

浏览器测试使用可选的 Playwright，脚本为 `project/tests/browser-smoke.cjs`。先用 `python project/tests/browser_fixture.py project/instance/browser-new.sqlite3` 创建独立的新测试数据库（含结束后的评价场景），再用 `python project/run.py serve --port 5002 --database project/instance/browser-new.sqlite3` 启动对应服务，设置 `BASE_URL` 为该服务地址并执行 `node project/tests/browser-smoke.cjs`。脚本会实际提交申请、审核、报名及任务变化，不能指向正在使用的数据库。

随后可在同一测试服务上执行 `node project/tests/browser-style.cjs`，检查本地字体、图表数据、悬停按压、状态配色和手机布局，截图写入已排除版本管理的 `test-results/`。字体来源及重新生成方法见 `project/src/campus_clubs/static/fonts/README.md`。

## 使用范围

这一版优先交付需求中的核心闭环。项目内置服务用于单机课程演示，默认只监听本机；实际校园部署仍需真实业务规则复核、正式账号管理、HTTPS、生产服务部署及负载验证。自动化测试结果仅证明对应场景，不能替代真实用户可用性测试或生产验收。

需求输入见 `labs/lab02-requirements/SRS.md`，设计与接口约定见 `docs/design/`。
