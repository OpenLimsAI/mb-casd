# 应用接入档案：dikw-kb（迈博知识库，OpenDIKW）

> 每个接入 IAM 中台的上层应用一份本档案，作为该应用 OIDC 配置与 RBAC 的**单一变更跟踪源**。

- 应用：[OpenDIKW](https://github.com/OpenDIKW) 知识库 —— dikw-core（知识引擎）+ dikw-web（Web 界面，OIDC 鉴权在 dikw-web 内实现）
- 鉴权实现：dikw-web 0.10.0 起的 OIDC / BFF 模式（[OpenDIKW/dikw-web#200](https://github.com/OpenDIKW/dikw-web/issues/200)，设计见该仓库 `docs/adr/0006-oidc-auth-bff.md`）
- 部署：maibo-prometheus 服务器 `~/dikw/`（服务 `dikw-core-v06` / `dikw-web-v06`），运维文档见 maibo 仓库 `docs/dikw-deploy.md`
- 接入状态：**生产运行**（2026-10-03 切换）

## 1. OIDC 客户端配置（Casdoor `application = admin/dikw-kb`）

| 项 | 值 |
|---|---|
| 组织 | `mabpharm` |
| 应用名 / 显示名 | `dikw-kb` / 迈博知识库 |
| 协议 | OIDC，授权码 + PKCE（S256），`state` / `nonce` 校验 |
| `grantTypes` | `authorization_code`（不需要 refresh token：dikw-web 会话绝对有效期 8 小时） |
| `tokenFormat` | JWT（`cert-built-in`），`expireInHours: 1` |
| 注册 | 关闭（`enableSignUp: false`），账号由管理员开通 |
| 回调 URI | `https://maibo-dikw.i-am-holo.top/web/auth/callback` |
| 登出回跳 | `https://maibo-dikw.i-am-holo.top/`（RP-initiated logout 走 Casdoor `/api/logout`） |
| Issuer（公网） | `https://iam.openlims.ai` |
| 服务端内网地址 | `http://casdoor:8000`（dikw-web 接入 `mb-pm-v2_internal` 网络；服务器访问不了公网 iam.openlims.ai） |
| clientId / clientSecret | 只在服务器 `~/dikw/.env`（`DIKW_WEB_OIDC_CLIENT_ID` / `DIKW_WEB_OIDC_CLIENT_SECRET`），不入库 |

> 应用配置以 `mp-pm` 应用为模板克隆（字段齐全），改了名称、回调、client 凭据和 grantTypes。

## 2. 角色（Casdoor 角色名 ⇄ dikw-web 权限级别）

| Casdoor 角色名 | dikw-web 级别 | displayName | 当前成员 |
|---|---|---|---|
| `kb_editor` | editor | 知识库编辑 | `mabpharm/guo.admin`、`mabpharm/hele.hl` |
| `kb_viewer` | viewer | 知识库只读 | `mabpharm/guo.cmc` |

- dikw-web 读取方式：`DIKW_WEB_OIDC_ROLES_CLAIM=roles[].name`，`DIKW_WEB_OIDC_ROLES_OWNER=mabpharm`（只认本组织、`isEnabled` 的角色对象）；`DIKW_WEB_ROLE_EDITOR=kb_editor`，`DIKW_WEB_ROLE_VIEWER=kb_viewer`。editor 包含 viewer。
- **与 mp-pm 共存**：mp-pm 只认自己的 6 个角色名并要求恰好一个，`kb_*` 不在其集合内会被忽略 —— 同一用户可同时持有一个 PM 角色和一个 kb 角色。新增知识库角色时**不要**与 PM 角色重名。
- 没有任何 kb 角色的已登录用户会看到「无访问权限」页面。角色变更在下次登录生效。

## 3. 权限矩阵（dikw-web 服务端强制）

| 能力 | viewer | editor |
|---|:-:|:-:|
| 浏览页面、图谱、任务（`GET /v1/*`），`POST /v1/retrieve`、`POST /v1/doc/search` | ✓ | ✓ |
| 与 agent 对话（仅自己的会话）、双语阅读（`/web/translate/*`） | ✓ | ✓ |
| 导入与文档转换（`POST /v1/import`、`/web/mineru/*`） | | ✓ |
| ingest / synth / eval、lint propose / apply、取消任务、写 wisdom | | ✓ |
| 确认 agent 维护提案 | | ✓ |

未列出的 dikw-core 写接口一律只给 editor。所有写请求要求 `Origin` 与 `https://maibo-dikw.i-am-holo.top` 完全一致（CSRF）。

## 4. 其他约定

- agent 会话按用户隔离：ADK `userId = oidc:<sub>`（`sub` = Casdoor 用户 id）。开启鉴权前的共享会话（`userId: demo`）交给 guo.admin（`DIKW_WEB_AUTH_LEGACY_SESSIONS_OWNER`）。
- 机器客户端（`dikw client` CLI、脚本）不走 IAM：带 dikw-core 的 Bearer token 直连 `/v1`（反向代理按 `Authorization` 头分流）。

## 5. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-10-03 | 应用注册 + 角色 | 新建应用 `admin/dikw-kb`（克隆自 mp-pm）；新建角色 `kb_editor`（guo.admin）、`kb_viewer`（guo.cmc）。改动前角色快照在服务器 `~/mb-pm-v2/private-config-backups/20261003T033822Z-dikw-oidc/` |
| 2026-10-03 | 验收（SSH 隧道） | 临时登记 `http://localhost:18090` 回调做验收；测试账号 `mabpharm/hele.hl`：editor（登录、Settings 无 token 输入、旧会话归属、agent 走服务端 token、Import 可用）与 viewer（编辑类接口 403、Import 隐藏、检索/对话可用）均通过 |
| 2026-10-03 | 生产切换 | 回调改为正式域名，删除 localhost 回调；`hele.hl` 留作管理员个人账号（kb_editor）；Cloudflare Access 删除，人侧鉴权完全由 IAM 承担 |
