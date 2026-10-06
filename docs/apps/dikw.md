# 应用接入档案：dikw-kb（迈博知识库，OpenDIKW）

> 每个接入 IAM 中台的上层应用一份本档案，作为该应用 OIDC 配置与 RBAC 的**单一变更跟踪源**。

- 应用：[OpenDIKW](https://github.com/OpenDIKW) 知识库 —— dikw-core（知识引擎）+ dikw-web（Web 界面，OIDC 鉴权在 dikw-web 内实现）
- 鉴权实现：dikw-web 0.10.0 起的 OIDC / BFF 模式，当前运行 0.11.0（[OpenDIKW/dikw-web#200](https://github.com/OpenDIKW/dikw-web/issues/200)，设计见该仓库 `docs/adr/0006-oidc-auth-bff.md`）
- 部署：maibo-prometheus 服务器 `~/dikw/`（服务 `dikw-core` / `dikw-web`），运维文档见 maibo 仓库 `docs/dikw-deploy.md`
- 接入状态：**生产运行**（2026-10-03 切换）

## 1. OIDC 客户端配置（Casdoor `application = admin/dikw-kb`）

| 项 | 值 |
|---|---|
| 组织 | `mabpharm` |
| 应用名 / 显示名 | `dikw-kb` / 迈博知识库 |
| 协议 | OIDC，授权码 + PKCE（S256），`state` / `nonce` 校验 |
| `grantTypes` | `authorization_code`、`refresh_token`（dikw-web ≥ 0.11.0 用 refresh token 续期会话并同步角色；无需 `offline_access`） |
| `tokenFormat` | JWT（`cert-built-in`），`expireInHours: 1`，`refreshExpireInHours: 168` |
| 注册 | 关闭（`enableSignUp: false`），账号由管理员开通 |
| 访问地址 | `https://kb.openlims.ai`（2026-10-03 起；旧域名 `maibo-dikw.i-am-holo.top` 已停用） |
| 主页地址（`homepageUrl`） | `https://kb.openlims.ai/#mb-web`：IAM 应用列表的入口直接打开论文知识库（MB-Web）；管理工作台在根地址 |
| 回调 URI | `https://kb.openlims.ai/web/auth/callback` |
| 登出回跳 | `https://kb.openlims.ai/`（RP-initiated logout 走 Casdoor `/api/logout`） |
| Issuer（公网） | `https://iam.openlims.ai` |
| 服务端访问 IdP | 经同名代理 `iam-proxy`（服务器 `~/iam-proxy`，配置与接入方法见 [`deploy/iam-proxy/`](../../deploy/iam-proxy/README.md)，取舍见 ADR-0003）：服务器访问不了公网 iam.openlims.ai，dikw-web 在专用网络 `iam-oidc` 上把 `iam.openlims.ai` 解析到代理，代理用自建 CA 提供 https，只放行 discovery、JWKS、token、userinfo、introspect，转发到 `casdoor:8000`。dikw-web 不再直连 Casdoor，也不再使用 `DIKW_WEB_OIDC_INTERNAL_URL` |
| clientId / clientSecret | 只在服务器 `~/dikw/.env`（`DIKW_WEB_OIDC_CLIENT_ID` / `DIKW_WEB_OIDC_CLIENT_SECRET`），不入库 |

> 应用配置以 `mp-pm` 应用为模板克隆（字段齐全），改了名称、回调、client 凭据和 grantTypes。
>
> ⚠️ **`refresh_token` 授权不能关**：Casdoor 3.100 的授权码响应总会带 `refresh_token`（不看应用是否开了该授权），dikw-web 拿到就按可续期会话处理，每约 15 分钟续期一次；授权一关，续期被拒（`unsupported_grant_type`），所有人登录 15 分钟后被登出。`refreshExpireInHours` 也不要设回 0（0 表示与 access token 同为 1 小时，闲置超过 1 小时续期就会失败）。

## 2. 角色（Casdoor 角色名 ⇄ dikw-web 权限级别）

| Casdoor 角色名 | dikw-web 级别 | displayName | 当前成员 |
|---|---|---|---|
| `kb_editor` | editor | 知识库编辑 | `mabpharm/guo.admin`、`mabpharm/hele.hl` |
| `kb_viewer` | viewer | 知识库只读 | `mabpharm/guo.cmc` |

- dikw-web 读取方式：`DIKW_WEB_OIDC_ROLES_CLAIM=roles[].name`，`DIKW_WEB_OIDC_ROLES_OWNER=mabpharm`（只认本组织、`isEnabled` 的角色对象）；`DIKW_WEB_ROLE_EDITOR=kb_editor`，`DIKW_WEB_ROLE_VIEWER=kb_viewer`。editor 包含 viewer。
- **与 mp-pm 共存**：mp-pm 只认自己的 6 个角色名并要求恰好一个，`kb_*` 不在其集合内会被忽略 —— 同一用户可同时持有一个 PM 角色和一个 kb 角色。新增知识库角色时**不要**与 PM 角色重名。
- 没有任何 kb 角色的已登录用户会看到「无访问权限」页面。角色变更在下次续期时同步（约 15 分钟内），不需要重新登录。

## 3. 权限矩阵（dikw-web 服务端强制）

| 能力 | viewer | editor |
|---|:-:|:-:|
| 浏览页面、图谱、任务（`GET /v1/*`），`POST /v1/retrieve`、`POST /v1/doc/search` | ✓ | ✓ |
| 与 agent 对话（仅自己的会话）、双语阅读（`/web/translate/*`） | ✓ | ✓ |
| 导入与文档转换（`POST /v1/import`、`/web/mineru/*`） | | ✓ |
| ingest / synth / eval、lint propose / apply、取消任务、写 wisdom | | ✓ |
| 确认 agent 维护提案 | | ✓ |

未列出的 dikw-core 写接口一律只给 editor。所有写请求要求 `Origin` 与 `https://kb.openlims.ai` 完全一致（CSRF）。

## 4. 其他约定

- agent 会话按用户隔离：ADK `userId = oidc:<sub>`（`sub` = Casdoor 用户 id）。开启鉴权前的共享会话（`userId: demo`）交给 guo.admin（`DIKW_WEB_AUTH_LEGACY_SESSIONS_OWNER`）。
- 机器客户端（`dikw client` CLI、脚本）不走 IAM：带 dikw-core 的 Bearer token 直连 `/v1`（反向代理按 `Authorization` 头分流）。

## 5. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-10-03 | 应用注册 + 角色 | 新建应用 `admin/dikw-kb`（克隆自 mp-pm）；新建角色 `kb_editor`（guo.admin）、`kb_viewer`（guo.cmc）。改动前角色快照在服务器 `~/mb-pm-v2/private-config-backups/20261003T033822Z-dikw-oidc/` |
| 2026-10-03 | 验收（SSH 隧道） | 临时登记 `http://localhost:18090` 回调做验收；测试账号 `mabpharm/hele.hl`：editor（登录、Settings 无 token 输入、旧会话归属、agent 走服务端 token、Import 可用）与 viewer（编辑类接口 403、Import 隐藏、检索/对话可用）均通过 |
| 2026-10-03 | 生产切换 | 回调改为正式域名，删除 localhost 回调；`hele.hl` 留作管理员个人账号（kb_editor）；Cloudflare Access 删除，人侧鉴权完全由 IAM 承担 |
| 2026-10-03 | dikw-web 升级 0.11.0 | 客户端配置不变；新版本支持 refresh token 续期与角色同步 |
| 2026-10-03 | 开启 refresh token | `grantTypes` 加 `refresh_token`，`refreshExpireInHours` 0 → 168；dikw-web 会话变为闲置 8 小时 / 最长 7 天，角色约 15 分钟同步。改前配置快照在服务器 `~/mb-pm-v2/private-config-backups/20261003T064742Z-dikw-refresh/` |
| 2026-10-03 | 删除应用 `admin/mb-kb` | 同事为 kb.openlims.ai 网关（kb-gateway）建的应用（回调 `/auth/callback`、`/login`）；dikw-web 原生 OIDC 取代该网关后删除，无关联角色 / 权限 / 用户。快照 `~/mb-pm-v2/private-config-backups/20261003T084502Z-mb-kb-delete/` |
| 2026-10-03 | 域名迁到 kb.openlims.ai | `redirectUris` 改为 `https://kb.openlims.ai/web/auth/callback`、`https://kb.openlims.ai/`，删除 `maibo-dikw.i-am-holo.top` 的两条；`homepageUrl` 改为 `https://kb.openlims.ai`。快照 `~/mb-pm-v2/private-config-backups/20261003T083815Z-dikw-kb-domain/`、`20261003T094930Z-dikw-kb-cutover/` |
| 2026-10-03 | 服务端改走 iam-proxy | 新增同名代理 `~/iam-proxy`（Caddy，自建 CA，专用网络 `iam-oidc`，只放行 5 个服务端 OIDC 路径）；dikw-web 去掉内网地址配置、退出 `mb-pm-v2_internal`。Casdoor 应用配置不变。discovery、续期换 token、JWKS 验签均已验证。后续 managed-agent console / platform 接入 IAM 复用此代理 |
| 2026-10-04 | 入口默认打开论文知识库 | `homepageUrl` 改为 `https://kb.openlims.ai/#mb-web`；mb-pm 的 www 工作台与「相关系统 → 知识库」同步改为该地址（OpenLimsAI/mb-pm#14，已上线）。未登录时 dikw-web 登录会保留 `#mb-web`。快照 `~/mb-pm-v2/private-config-backups/20261004T150856Z-dikw-kb-homepage/` |
| 2026-10-06 | 计划：改给论文知识库 | dikw-web 0.12 起论文知识库拆成独立应用 dikw-mbweb。拆分部署时，`kb.openlims.ai` 交给 dikw-mbweb，**继续使用本应用 `dikw-kb`**：回调、角色、续期设置都不变，`kb_viewer` = 查看、`kb_editor` = 上传和发布。管理工作台改用新应用 `admin/dikw-web`（见 [`dikw-web.md`](dikw-web.md)，角色 `dikw-admin`）。切换后再更新本档案的应用说明、`homepageUrl` 和权限矩阵 |
