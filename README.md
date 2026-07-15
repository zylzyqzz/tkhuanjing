# JC开播助手

面向 TikTok 电脑直播公司和工作室的开播前技术准备度检测系统。V2.4 包含双模式 PySide6 客户端、FastAPI 后台、Vue 管理端、硬安装程序和独立更新助手。

V2.4 以“一键开播检查 / 一键配置环境”双模式和“真实数据—问题定位—处理方案—自动复检”为主线。公网 IP 纯净度属于第三方辅助情报，产品不会据此承诺账号审核、流量或平台结果。

## 本地开发

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test,build]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m server.migrate --legacy local_test_data\database\platform.sqlite3
.\.venv\Scripts\python -m uvicorn server.main:app --reload
.\.venv\Scripts\python -m client_v2.main
```

管理后台：`http://127.0.0.1:8000/tk-admin/`  
公开下载页：`http://127.0.0.1:8000/download/`

## 本地管理后台程序

`TK管理后台本地安装程序-2.2.0.exe` 安装到
`%LOCALAPPDATA%\Programs\WeiDuTKAdminLocal`，并在桌面创建“启动 TK 管理后台”和
“停止 TK 管理后台”快捷方式。程序只监听 `127.0.0.1:8000`，不会随 Windows 自动启动。

本机数据库、日志和随机密钥保存在安装目录的 `runtime` 中；覆盖安装和卸载不会主动删除
数据库。管理员密码通过维护工具写入 Argon2 哈希，密码明文不进入源码或安装包配置。

本地后台安装包构建命令：

```powershell
C:\tkv2env\Scripts\pyinstaller.exe --clean --noconfirm --distpath dist_admin_local --workpath build_admin_local admin_local.spec
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer_admin_local.iss
```

## 测试与构建

```powershell
.\scripts\test.ps1
.\scripts\build.ps1
```

构建前必须通过自动测试。正式环境的密码、会话密钥、授权密钥和更新签名私钥只能通过环境变量提供，严禁提交到仓库。
