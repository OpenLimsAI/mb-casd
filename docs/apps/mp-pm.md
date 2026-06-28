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
| clientId / clientSecret | 由 Casdoor 生成；记入 mp-pm 的 `.env`，不入库 |

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
- [ ] 引入 `oidc-client-ts`（或 `casdoor-js-sdk`），授权码 + PKCE
- [ ] 新增 `/callback` 路由页
- [ ] 改 `src/store/auth.ts`：`currentUser` 从已验证 token 的角色 claim 解析；保留 `useAuth` 接口形态
- [ ] 未登录重定向到 Casdoor 授权端点

后端：
- [ ] JWKS 验签中间件（复用 `python-jose`）
- [ ] 从 claims 解析用户 + 角色，映射到 `Role`
- [ ] 受保护接口按角色鉴权
- [ ] 确认角色 claim 的确切字段名/结构，固化映射（见第 5 节）

## 5. 变更记录

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-06-28 | 初始档案 | 角色/权限矩阵取自 mp-pm 当前代码；OIDC 配置待 P4 落地核对 |
