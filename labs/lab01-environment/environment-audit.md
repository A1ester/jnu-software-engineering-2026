# 实验环境审计

审计日期：2026-09-20。以下值来自本机实际命令；Windows 版本号是系统 API 返回值，未据此推断具体发行名称。

| 项目 | 实测结果 | 命令/来源 |
|---|---|---|
| 操作系统 | Microsoft Windows NT 10.0.26200.0 | `[System.Environment]::OSVersion.VersionString` |
| Git | 2.52.0.windows.1 | `git --version` |
| Python | 3.12.2 | `python --version`、`py --version` |
| VS Code | 1.137.0 | `code --version` |
| GitHub CLI | 2.96.0 | `gh --version` |
| Git 用户名 | A1ester | `git config --global user.name` |
| Git 邮箱 | 19558788851@163.com | `git config --global user.email` |
| GitHub CLI 登录 | 已登录 github.com，账号 A1ester，HTTPS 协议 | `gh auth status`；令牌已遮盖 |

仓库仅位于指定子目录。本文件为审计记录，不包含凭据。
