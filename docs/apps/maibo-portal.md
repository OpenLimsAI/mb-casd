# 应用接入档案：maibo-portal（迈博药业员工门户）

> 每个接入 IAM 中台的上层应用一份本档案，作为该应用 OIDC 配置与 RBAC 的**单一变更跟踪源**。

- 应用：员工门户 `https://www.openlims.ai`。登录后按 IAM 角色显示用户能打开的应用（项目管理、论文知识库）。
- 代码：mb-pm 仓库的一部分，和 PM 共用后端（`backend/app/api/v1/portal.py`，路由 `/api/v1/portal/*`），见 OpenLimsAI/mb-pm#12。
- 部署：maibo-prometheus 服务器的 PM 栈 `~/mb-pm-v2`，和 PM 同一个容器。
- 接入状态：**生产运行**（2026-10-04 上线）。

## 1. OIDC 客户端配置（Casdoor `application = admin/maibo-portal`）

2026-10-08 从生产 IAM 核对。

| 项 | 值 |
|---|---|
| 组织 | `mabpharm` |
| 应用名 / 显示名 | `maibo-portal` / 迈博药业员工门户 |
| 协议 | OIDC，授权码 + PKCE（S256），`state` / `nonce` 校验，后端换 token，token 不进浏览器 |
| `grantTypes` | `authorization_code`、`refresh_token` |
| `tokenFormat` | JWT（`cert-built-in`），`expireInHours: 1` |
| 注册 | 关闭（`enableSignUp: false`），账号由管理员开通 |
| 主页地址（`homepageUrl`） | `https://www.openlims.ai` |
| 回调 URI | `https://www.openlims.ai/api/v1/portal/callback` |
| 登出回跳 | `https://www.openlims.ai/login`（RP-initiated logout 走 Casdoor `/api/logout`） |
| 单点登录 | `enableSigninSession: true`、`enableAutoSignin: true`、`cookieExpireInHours: 168`（见 ADR-0004） |
| clientId / clientSecret | 只在服务器 PM 栈的 `.env`（`PORTAL_CLIENT_ID` / `PORTAL_CLIENT_SECRET`），不入库 |

- 门户会话最长 1 小时（PM 后端 `IAM_SESSION_SECONDS` 默认 3600），不续期。到期后重新走授权；IAM 会话还在时自动登录。
- 门户退出时，请求 Casdoor `/api/logout` 清掉 IAM 会话。`pm.openlims.ai` 和 `kb.openlims.ai` 上的会话不受影响，要在各自应用里退出（门户的 cookie 只对 `www` 有效）。

## 2. 角色与准入

门户本身不需要角色：`mabpharm` 组织里未停用、未删除的账号都能登录门户。

应用卡片是否可用，按 IAM 角色判断：

| 应用卡片 | 可用条件 |
|---|---|
| 项目管理 | 恰好一个 PM 角色（`admin` / `cmc_lead` / `project_lead` / `rd` / `production` / `qa_qc`），并且 PM 里有同用户名的启用成员（见 [`mp-pm.md`](mp-pm.md)） |
| 知识库 | 有 `kb_viewer` 或 `kb_editor`（见 [`dikw.md`](dikw.md)） |

- 门户只显示入口，不给权限。进入应用后，以应用自己的检查为准。
- 门户不自动创建 PM 成员，也不自动分配角色。

## 3. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-10-03 | 应用注册 | 同事为员工门户新建 `admin/maibo-portal`（Casdoor 创建时间 19:46 UTC）。门户随 OpenLimsAI/mb-pm#12 上线（2026-10-04） |
| 2026-10-07 | 开启单点登录 | `enableSigninSession`、`enableAutoSignin` 打开，`cookieExpireInHours` 0 → 168，见 ADR-0004。快照 `~/mb-pm-v2/private-config-backups/20261007T232541Z-sso-session/`。Chrome 验证：在知识库登录后，门户直接进入，不用再输密码 |
