# VD Nexus 2.1 Phase 0 / Phase 1 兼容说明

本轮为增量升级。`Customer` 表继续作为企业数据源，`Admin` 继续承担平台超级管理员，企业成员使用新增的 `organization_members`。旧 `/api/v1`、旧报告和旧后台表均不删除。

## 数据库迁移

新环境或已有环境均执行：

```bash
alembic upgrade head
```

服务端容器镜像已包含 Alembic 配置和 revisions，并在启动 API 前执行同一条升级命令；迁移失败时容器不会继续启动旧结构上的新 API。

`20260721_00` 是 V1 基线：空库会建立遗留表，已有库只补充不存在的表且不会清除数据。`20260721_01` 建立 Phase 0/1 的企业成员、账号、主播、绑定历史和心跳表。回退到基线只移除 Phase 0/1 新表，不删除 V1 表。

生产及预发布建议使用 PostgreSQL 16 与 `postgresql+psycopg://`，本地仍支持 SQLite。新表时间列均使用 timezone-aware datetime。

## API 与租户隔离

- V1 保持 `/api/v1`，不改变旧客户端契约。
- Phase 0/1 使用 `/api/v2`。
- 企业成员 Bearer 会话由服务端确定 `organization_id`，业务查询不接受前端传入企业 ID 作为租户依据。
- 设备使用 `X-Device-Token`，绑定变更同时要求企业成员权限。
- 绑定、解绑、企业成员角色变更均写入旧 `AuditLog`，供现有审计后台继续读取。
- 一台设备和一个直播间最多各有一个 active primary 绑定；换绑结束旧记录并新建版本，不覆盖历史。
- 新主绑定同步回写旧 `Device.customer_id` 和 `Device.room_id`，旧后台可继续显示当前归属。

## 客户端安全边界

心跳仅上传版本、在线/采集状态、直播软件进程状态和轻量资源指标。不采集 TikTok 密码、Cookie、浏览器会话、屏幕或直播素材。服务端响应只允许 `refresh_config`、`sync_binding` 两种无命令执行能力的配置动作；其他命令会被客户端拒绝并保留离线队列。

本阶段不实现真实直播数据抓取、远程系统命令、TikTok 内部控件操作、场次指标或 AI 分析。
