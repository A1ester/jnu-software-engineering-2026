# 临时云端测试部署

用于验证 Linux 服务器上的安装、HTTPS 访问、账号登录和业务操作。使用独立测试数据库，页面明确显示测试标识。入口采用 Gunicorn，默认 1 个进程、4 个线程；不需要 GPU。平台的公网访问权限及使用范围需以其当前控制台和规则为准。

## 本机准备

在已有项目虚拟环境中生成一次性测试访问资料，输出目录必须是新目录：

```powershell
.\.venv\Scripts\python.exe project/deploy/prepare-cloud-test.py --profile project/instance/club-profile.json --output-dir project/instance/cloud-test-new --url https://站点地址
```

`access.json` 包含站点访问账号、随机口令、负责人账号和随机测试密码，仅保留在本机受限目录中。`bootstrap.json` 只包含经确认的社团资料和口令摘要，可上传到独立测试部署目录。运行数据和访问文件均位于 Git 排除范围；不要上传本机业务数据库、会话、私钥或 SSH 密码。

## 服务器初始化

将代码中的 `project/` 目录和 `bootstrap.json` 上传到新部署目录。以下示例以 `/root/autodl-tmp/jnu-clubs-cloud-test` 为部署目录，Python 路径按服务器实际情况替换：

```bash
cd /root/autodl-tmp/jnu-clubs-cloud-test
/root/miniconda3/bin/python -m venv venv
venv/bin/python -m pip install -r project/requirements-cloud-test.txt
venv/bin/python project/deploy/initialize-cloud-test.py bootstrap.json runtime
bash project/deploy/start-cloud-test.sh /root/autodl-tmp/jnu-clubs-cloud-test
```

初始化只接受新的运行目录。它生成课程演示数据和经确认的社团介绍，不生成真实活动、真实成员名单或学校批准记录；演示角色用于流程测试。负责人测试密码与本机账号密码相互独立。

`runtime/service.env` 保存数据库路径、测试访问账号和口令摘要。访问口令必须是准备工具生成的高强度随机值；缺少有效配置时服务拒绝启动。所有网页、API 和静态资源均受访问口令保护；平台 HTTPS 入口负责 TLS，应用会话 Cookie 标记为 Secure、HttpOnly 和 SameSite=Lax。

启动脚本检查端口占用，不终止其他进程。Gunicorn 在后台运行，PID 位于 `runtime/gunicorn.pid`，日志位于 `runtime/logs/`；日志不记录认证头或查询参数。关闭 SSH 窗口后服务继续运行，但实例关机后需要重新执行启动命令。

## 浏览器验证

使用可选 Playwright，在本机设置 `CLOUD_TEST_ACCESS_FILE` 指向私有 `access.json`，执行：

```powershell
node project/tests/browser-cloud.cjs
```

该测试会核验 HTTPS 访问口令、学生和负责人及管理角色登录、社团资料、权限边界和手机布局，并在演示社团创建明确标注的测试活动，完成审核、报名及取消。它不在真实社团中创建活动。截图写入 Git 排除的 `test-results/`。

## 停止与再次启动

```bash
bash project/deploy/stop-cloud-test.sh /root/autodl-tmp/jnu-clubs-cloud-test
bash project/deploy/start-cloud-test.sh /root/autodl-tmp/jnu-clubs-cloud-test
```

停止脚本核对 PID 对应进程的工作目录和命令，只停止本部署的 Gunicorn。重新启动保留独立数据库。停止网站进程不会关闭云实例，测试结束后还需在平台控制台关机。

依赖和 Gunicorn 用法参考 [PyPI](https://pypi.org/project/gunicorn/) 与 [官方文档](https://gunicorn.org/)；该流程只验证临时云端测试，不表示长期生产部署验收完成。
