# VD Nexus V2.1

VD Nexus 是面向 TikTok 电脑直播的开播前环境检测工具。当前版本只生成三类结果：

- 网络环境报告与建议；
- 影响开播的 Windows 系统环境检查与一键修复；
- 电脑性能说明与建议。

网络和性能结果仅提供建议，只有明确的系统环境失败或未完成会阻止客户端展示“开始开播”。客户端不读取 TikTok 密码、Cookie、个人文件或直播素材，也不代替用户操作直播软件内部控件。

## 组件

- `client_v2/`：PySide6 Windows 客户端，唯一窗口入口为 `AppWindow`。
- `server/`：FastAPI 授权、报告、更新和管理 API。
- `admin/`：Vue 管理后台。
- `deploy/`：生产与预发容器配置。
- `tests_v2/`：业务、API、安全和 Qt 集成测试。

## Windows 本地开发

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test,build]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m server.migrate
.\.venv\Scripts\python -m uvicorn server.main:app --reload
.\.venv\Scripts\python -m client_v2.main
```

管理后台：`http://127.0.0.1:8000/tk-admin/`；健康检查：`http://127.0.0.1:8000/health`。

## 测试与发布

```powershell
.\scripts\test.ps1
.\scripts\build.ps1
```

发布流水线固定执行测试、静态编译、后台构建、Windows 客户端构建、签名与哈希校验。生产发布前必须备份数据库与运行配置，并在预发端口完成健康检查。

密码、SSH 私钥、会话密钥、授权密钥和更新签名私钥只能通过受限环境或密钥服务注入，严禁提交到仓库。
