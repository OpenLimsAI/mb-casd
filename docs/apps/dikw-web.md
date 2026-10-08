# 应用接入档案：dikw-web（知识库管理工作台，OpenDIKW）

> 每个接入 IAM 中台的上层应用一份本档案，作为该应用 OIDC 配置与 RBAC 的**单一变更跟踪源**。

- 应用：[OpenDIKW/dikw-web](https://github.com/OpenDIKW/dikw-web) 管理工作台（导入、任务、lint、agent 维护等），和论文知识库 dikw-mbweb 共用同一个 dikw-core 知识库。
- 背景：dikw-web 0.12 起，论文知识库（MB-Web）拆成独立的私有应用 `dikw-mbweb`。拆分后：
  - `kb.openlims.ai` 交给 dikw-mbweb，沿用应用 `dikw-kb`（见 [`dikw.md`](dikw.md)）；
  - 工作台改用本应用，只开放给知识库管理员。
- 部署：maibo-prometheus 服务器 `~/dikw/`，服务 `dikw-web`，当前镜像 `dikw-web:0.12.4`（2026-10-06 起，2026-10-08 核对）。运维文档见 maibo 仓库 `docs/dikw-deploy.md`。
- 接入状态：**生产运行**（2026-10-06 拆分切换后上线；访问地址暂为 localhost + SSH 隧道）

## 1. OIDC 客户端配置（Casdoor `application = admin/dikw-web`）

| 项 | 值 |
|---|---|
| 组织 | `mabpharm` |
| 应用名 / 显示名 | `dikw-web` / 知识库管理工作台 |
| 来源 | 克隆自 `dikw-kb`（字段齐全），改了名称、显示名、client 凭据、回调和主页地址 |
| 协议 | OIDC，授权码 + PKCE（S256），`state` / `nonce` 校验 |
| `grantTypes` | `authorization_code`、`refresh_token`（**`refresh_token` 不能关**，原因同 `dikw.md` 第 1 节） |
| `tokenFormat` | JWT（`cert-built-in`），`expireInHours: 1`，`refreshExpireInHours: 168` |
| 注册 | 关闭（`enableSignUp: false`） |
| 单点登录 | `enableSigninSession: true`、`enableAutoSignin: true`、`cookieExpireInHours: 168`（2026-10-07 起，见 ADR-0004） |
| 访问地址 | 临时：管理员经 SSH 隧道访问 `http://localhost:4330`（服务器只监听 `127.0.0.1:4330`）。计划：`https://kb-admin.openlims.ai`，等同事在 Cloudflare 隧道加公开主机名 |
| 回调 URI | 临时 `http://localhost:4330/web/auth/callback`（登出回跳 `http://localhost:4330/`）；改用正式域名时换成 `https://kb-admin.openlims.ai/...` |
| 主页地址（`homepageUrl`） | 空（临时地址是 localhost，不在 IAM 应用列表里放入口） |
| 服务端访问 IdP | 同 `dikw.md`：经同名代理 `iam-proxy`（专用网络 `iam-oidc`，`NODE_EXTRA_CA_CERTS`） |
| clientId / clientSecret | 只在服务器 `~/dikw/dikw-web-oidc.private`（0600），切换时写入工作台的环境变量，不入库 |

## 2. 角色

| Casdoor 角色名 | dikw-web 级别 | displayName | 当前成员 |
|---|---|---|---|
| `dikw-admin` | editor | 知识库管理员 | `mabpharm/guo.admin`、`mabpharm/hele.hl` |

- dikw-web 读取方式：`DIKW_WEB_OIDC_ROLES_CLAIM=roles[].name`，`DIKW_WEB_OIDC_ROLES_OWNER=mabpharm`，只配 `DIKW_WEB_ROLE_EDITOR=dikw-admin`，不配 viewer（dikw-web 允许只配其中一个）。
- 没有 `dikw-admin` 的已登录用户会看到「无访问权限」。`kb_viewer` / `kb_editor` 只对论文知识库（`dikw-kb`）生效，不能进工作台。
- 和 mp-pm 共存：`dikw-admin` 不是 PM 的 6 个角色名之一（PM 有自己的 `admin`），mp-pm 会忽略它。

## 3. 权限矩阵

只有一个级别：持有 `dikw-admin` 就是 editor，拥有 `dikw.md` 第 3 节 editor 列的全部能力（导入与转换、ingest / synth / eval、lint、取消任务、写 wisdom、确认 agent 维护提案、对话与检索）。

## 4. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-10-06 | 应用注册 + 角色 | 新建应用 `admin/dikw-web`（克隆自 `dikw-kb`）和角色 `kb_admin`（guo.admin、hele.hl）。回调临时用 `http://localhost:4330`，主页地址留空。已验证：localhost 回调通过 Casdoor 校验，其他回调被拒；`dikw-kb` 未变。改动前快照在服务器 `~/mb-pm-v2/private-config-backups/20261006T043320Z-dikw-web-app/` |
| 2026-10-06 | 角色改名 | 按统一命名规范，`kb_admin` 换成 `dikw-admin`：先新建 `dikw-admin`（成员不变：guo.admin、hele.hl），确认无权限规则和父角色引用后删除 `kb_admin`。当时还没有服务使用该角色。快照 `~/mb-pm-v2/private-config-backups/20261006T043638Z-kb_admin-to-dikw-admin/` |
| 2026-10-06 | 上线 | 拆分切换（06:03 UTC）：管理工作台 `dikw-web:0.12.2` 使用本应用。服务器只监听 `127.0.0.1:4330`，管理员经 SSH 隧道访问。client 凭据在服务器 `.env` 的 `WORKBENCH_OIDC_*` 里，`dikw-web-oidc.private` 已删除。Chrome 验收通过：用 hele.hl 登录（Editor）；概览数据正确；在 Tasks 页点 Synth，只处理了 1 篇未完成的源文档，0 错误，新建 16 页 |
| 2026-10-07 | 开启单点登录 | 和其他 3 个 `mabpharm` 应用一起打开 `enableSigninSession`、`enableAutoSignin`，`cookieExpireInHours` 0 → 168，见 ADR-0004。快照 `~/mb-pm-v2/private-config-backups/20261007T232541Z-sso-session/`。工作台需要 SSH 隧道，这次没有在浏览器里验证 |
