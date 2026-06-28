# 应用接入档案：mp-pm（CMC 项目管理系统）

> 每个接入 IAM 中台的上层应用一份本档案，作为该应用 OIDC 配置与 RBAC 的**单一变更跟踪源**。

- 应用代码库：`/Users/hele/Projects/openlims/mp-pm`
- 技术栈：前端 Vite + React + TS（端口 5175，`strictPort`）；后端 FastAPI + SQLAlchemy + PostgreSQL，已用 `python-jose[cryptography]`
- 接入状态：规划中（本期 P4 端到端接入）

## 1. OIDC 客户端配置（Casdoor `application = mp-pm`）

| 项 | 值 |
|---|---|
| 组织 | `mabpharm` |
| 应用名 | `mp-pm` |
| 协议 | OIDC，授权码 + PKCE |
| `grantTypes` | `authorization_code`, `refresh_token` |
| `tokenFormat` | JWT |
| 签名证书 | `cert-built-in`（Casdoor 内置） |
| 回调 URI（dev） | `http://localhost:5175/callback` |
| 授权端点 | `http://localhost:8000/login/oauth/authorize` |
| Token 端点 | `http://localhost:8000/api/login/oauth/access_token` |
| JWKS | `http://localhost:8000/.well-known/jwks` |
| OIDC discovery | `http://localhost:8000/.well-known/openid-configuration` |
| clientId | `mppm-client-id-0001` |
| clientSecret | `mppm-client-secret-0001-change-me`（生产前务必轮换） |

> dev 端点用 `localhost:8000`；后续生产换为正式域名时，同步更新此表与 Casdoor 应用配置。

## 2. 角色（Casdoor 角色名 ⇄ mp-pm `Role`）

命名刻意与 mp-pm 代码内 `Role` 一致，避免翻译层。来源：`mp-pm/src/types.ts`、`mp-pm/src/lib/permissions.ts`。

| Casdoor 角色名 | mp-pm `Role` | displayName |
|---|---|---|
| `admin` | `admin` | 系统管理员 |
| `cmc_lead` | `cmc_lead` | CMC 负责人 |
| `project_lead` | `project_lead` | 项目负责人 |
| `rd` | `rd` | 工艺开发 |
| `production` | `production` | 生产支持 |
| `qa_qc` | `qa_qc` | QA/QC |

约定：本期一个用户分配**一个**角色（匹配 mp-pm 单角色模型 `User.role`）。

## 3. 权限矩阵（mp-pm 内部，角色→权限）

> RBAC 职责划分：**Casdoor 管角色分配；下表的细粒度权限判定保留在 mp-pm 代码内**（`src/lib/permissions.ts`）。此表为该矩阵的文档快照，代码变更时同步更新本表并在第 5 节记录。

| 权限 Key | admin | cmc_lead | project_lead | rd | production | qa_qc |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| project.create | ✓ | ✓ | | | | |
| project.delete | ✓ | ✓ | | | | |
| template.edit | ✓ | ✓ | | | | |
| template.import | ✓ | ✓ | | | | |
| template.export | ✓ | ✓ | | | | |
| subproject.create | ✓ | ✓ | ✓ | | | |
| task.create | ✓ | ✓ | ✓ | | | |
| task.update | ✓ | ✓ | ✓ | | | |
| task.update.own | | | | ✓ | ✓ | ✓ |
| dashboard.manager | ✓ | ✓ | ✓ | | | |
| workload.view | ✓ | ✓ | ✓ | | | |
| workload.recommend | ✓ | ✓ | ✓ | | | |
| dashboard.personal | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| gantt.view | ✓ | ✓ | ✓ | | | |
| gantt.view.own | | | | ✓ | ✓ | ✓ |
| gantt.edit | ✓ | ✓ | ✓ | | | |
| calendar.view | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| calendar.edit | ✓ | ✓ | ✓ | | ✓ | |
| system.config | ✓ | | | | | |
| user.manage | ✓ | | | | | |
| data.export | ✓ | ✓ | ✓ | | | ✓ |
| deviation.review | ✓ | ✓ | | | | ✓ |
| batch.release | ✓ | | | | | ✓ |

## 4. 接入改造清单（本期 P4）

前端：
- [x] 引入 `oidc-client-ts`（或 `casdoor-js-sdk`），授权码 + PKCE
- [x] 新增 `/callback` 路由页
- [x] 改 `src/store/auth.ts`：`currentUser` 从已验证 token 的角色 claim 解析；保留 `useAuth` 接口形态
- [x] 未登录重定向到 Casdoor 授权端点
- [x] 登出（RP-initiated logout）：`src/lib/oidc.ts` 的 `logout()` 清两处本地会话（oidc user + axios JWT）后跳 Casdoor `/api/logout`，清其 SSO 会话；TopBar 加「登出」入口

后端：
- [x] JWKS 验签中间件（复用 `python-jose`）
- [x] 从 claims 解析用户 + 角色，映射到 `Role`
- [x] 受保护接口按角色鉴权
- [x] 确认角色 claim 的确切字段名/结构，固化映射（见第 5 节）

  **已确认 token claim 形状（RS256，JWKS 验签通过）：**
  - `iss` = `http://localhost:8000`
  - `aud` = `["mppm-client-id-0001"]`（数组）
  - 身份：`name` claim 存放用户名（如 `guo.cmc`）；**`preferred_username` 不存在**，后端取 `name`
  - 角色：`roles` claim 为角色**对象数组**，例如 `[{"owner":"mabpharm","name":"cmc_lead","displayName":"CMC 负责人",...}]`；后端取 `roles[0].name`（无 flat `role` 字段）

## 5. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-06-28 | 初始档案 | 角色/权限矩阵取自 mp-pm 当前代码；OIDC 配置待 P4 落地核对 |
| 2026-06-28 | OIDC 应用注册（P3a） | 在 Casdoor 注册 mp-pm 应用（init_data.json），clientId=mppm-client-id-0001，PKCE 授权码流程，回调 http://localhost:5175/callback |
| 2026-06-28 | 端到端联调通过（P4c） | 端到端接入联调通过；确认 token 角色 claim 形状（roles 数组对象，取 roles[].name；身份取 name claim）；负向 RBAC 验证：rd→403，无 token/篡改 token→401 |
| 2026-06-29 | 后端 Docker 化 + 运行拓扑固化 | mp-pm 后端容器化（宿主 `8080`→容器 `8000`，避开 Casdoor 占用的 8000）；容器内 JWKS 走 `host.docker.internal`，issuer 仍校验 `localhost:8000`（`CASDOOR_JWKS_URL` 与 `CASDOOR_ENDPOINT` 解耦）；前端 `.env.local` 须指向 8080；前端 auth gate 修复（`ReadyGate` / 无 token 跳 Casdoor）。建表改用 SQLAlchemy `create_all`（alembic 迁移与模型漂移）。详见第 6 节 |
| 2026-06-29 | 登出（RP-initiated logout） | 补 `logout()`：清 oidc user + axios JWT，跳 Casdoor `/api/logout` 清 SSO 会话；TopBar 加「登出」；新增 `VITE_OIDC_POST_LOGOUT_REDIRECT_URI`（缺省回落 origin）。本地登出回跳 `http://localhost:5175/` 因 localhost 源免注册放行（生产需登记） |
| 2026-06-29 | 多账号登录/登出走查（验收通过） | Chrome 走查 6 个种子账号各自登录 + 登出全部通过：admin/张管理、guo.cmc/郭主任、li.pm1/李项目、liu.usp1/刘上游、mao.prod1/毛生产、qa.zhao/赵质量。角色门控 UI 正确：admin & cmc_lead 见「创建项目/创建模板/添加成员」，project_lead/rd/production/qa_qc 均不见。每次登出均落到 Casdoor 登录页空表单、换登显示**新用户本人**（≥6 次切换无静默重登）→ SSO 会话确实被清。存档 `mp-pm-multi-user-logout.gif` |

## 6. 本地运行拓扑（Docker）

全栈本地运行（2026-06-29 起，端到端 Chrome 走查通过）。

| 组件 | 启动方式 | 端口/容器 |
|---|---|---|
| Casdoor + 其 Postgres | `cd mb-casd && docker compose up -d` | Casdoor `:8000`；PG `127.0.0.1:5432`（仅回环） |
| mp-pm 后端 + 其 Postgres | `cd mp-pm/backend && docker compose up -d` | API 容器 `cmc-pms-api` 宿主 `8080`→容器 `8000`；PG `cmc-pms-pg` 仅 compose 网络内可达（不暴露宿主） |
| mp-pm 前端 | `cd mp-pm && npm run dev` | Vite `:5175`（dev server，未容器化） |

关键约定与坑位：

- **端口 8080 而非 8000**：宿主 8000 已被 Casdoor 占用，后端容器映射为 `8080:8000`，前端 `VITE_API_URL` 须为 `http://localhost:8080/api/v1`。
- **JWKS 拉取 vs issuer 校验解耦**：容器内 `localhost` 指向容器自身，拉不到宿主上的 Casdoor。后端用 `CASDOOR_JWKS_URL=http://host.docker.internal:8000/.well-known/jwks` 拉公钥，但 issuer 仍按 token 的 `iss`（浏览器侧 `http://localhost:8000`，即 `CASDOOR_ENDPOINT`）校验。二者由 `config.py` 的 `casdoor_jwks_url` 属性解耦。
- **`.env.local` 优先级坑**：Vite 中 `.env.local`（gitignored）覆盖 `.env`。曾因 `.env.local` 残留 `VITE_API_URL=...:8000`（= Casdoor）导致前端打到 Casdoor、报 `items is not iterable`。本机须改为 8080；`.env`/`.env.example` 已正确。
- **建表**：容器启动用 SQLAlchemy `Base.metadata.create_all` 从 ORM 模型建表，不跑 alembic（现有迁移与模型漂移，缺 `project_finances` 等表）。换新库需 `docker compose down -v`。
- **前端 auth gate**：`App.tsx` 的 `<ReadyGate>` 只包裹应用路由（`/callback` 在其外，始终可渲染）；`bootstrap()` 无 token 时重定向到 Casdoor 而非渲染未登录态。
- **登出回跳**：`logout()` 跳 Casdoor `/api/logout` 带 `post_logout_redirect_uri=http://localhost:5175/`。Casdoor 的 `IsValidOrigin` 对任意 `http://localhost` 源直接放行，故本地**无需在应用 `redirectUris` 注册**该回跳地址。登出后整页回到 `/` → `bootstrap` 无 token → 跳 Casdoor 登录页（SSO 已清，不会静默登回上一用户）。生产换真实域名后此免注册失效，须把登出回跳地址登记进 Casdoor 应用（且因 `initDataNewOnly=true`，改 init_data.json 对既有库不生效，要走 admin UI 或重置库）。

> 生产部署时本节失效：届时前端构建为静态资源由后端同源托管、统一域名 + 反代、JWKS/issuer 同源，无需 `host.docker.internal` 与跨端口 hack。
