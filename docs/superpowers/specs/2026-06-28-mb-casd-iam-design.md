# 迈博药业 IAM 中台（mb-casd）实施方案设计

- 状态：待评审
- 日期：2026-06-28
- 工作目录：`/Users/hele/Projects/openlims/mb-casd`
- 上游参考：本地 casdoor 源码 `/Users/hele/Projects/casdoor`（`v3.100.0`）

## 1. 目标与背景

基于 Casdoor 为迈博药业（mabpharm）搭建 IAM 中台：

1. 定制化（迈博品牌）的管理界面；
2. 为上层应用提供「用户名/密码登录 + 鉴权」服务，基于 RBAC 做访问控制；
3. 后台数据库使用 Postgres docker 实例；
4. 本机 docker 环境部署定制化的 Casdoor 实例（最新 release）。

第一个试点上层应用是 **mp-pm**（CMC 项目管理系统，`/Users/hele/Projects/openlims/mp-pm`）。

## 2. 已锁定的关键决策

| # | 决策 | 选择 |
|---|---|---|
| D1 | UI 定制深度 | **仅品牌化，用官方预构建镜像 `casbin/casdoor`，不改源码** |
| D2 | 目标环境 | **本机开发/POC 优先**；生产加固（TLS/反代/密钥/备份）留到后续阶段 |
| D3 | 登录接入方式 | **OIDC 授权码 + PKCE**，上层应用重定向到 Casdoor 托管登录页 |
| D4 | 语言 | **仅中文**（强制中文，无语言切换） |
| D5 | 数据库 | Postgres docker 实例 |
| D6 | 本次迭代范围 | **端到端闭环**：含 mp-pm 的客户端接入代码改造（跨 mb-casd + mp-pm 两仓） |
| D7 | RBAC 职责划分 | Casdoor 管「身份 + 角色分配」；mp-pm 保留其代码内既有「角色→权限」矩阵 |

## 3. 总体架构

```
┌─────────────┐   OIDC 授权码+PKCE     ┌──────────────────────┐
│  浏览器用户  │ ───重定向登录页────▶  │   Casdoor (官方镜像)   │
│             │ ◀──回跳带 token────    │   :8000               │
└─────────────┘                       │  · 托管登录页/管理台    │
       │                              │  · OIDC/OAuth2 Provider │
       │ 访问业务                      │  · Casbin RBAC          │
       ▼                              │  · 迈博品牌化            │
┌─────────────┐   JWT 验签(JWKS)      └──────────┬────────────┘
│   mp-pm      │ ◀───────────────────────────────┤ xorm
│  前端(Vite)  │   roles claim → 角色             │
│  后端(FastAPI)│                                 ▼
└─────────────┘                       ┌──────────────────┐
                                      │  Postgres :5432   │
                                      │  (docker, 持久卷)  │
                                      └──────────────────┘
```

- **Casdoor** = IAM 中台本体：托管登录页、管理控制台、OIDC Provider、Casbin RBAC、迈博品牌化。
- **Postgres** = 后台库（docker 实例，命名卷持久化，凭证走 `.env`）。
- **mp-pm** = 首个 OIDC 客户端：前端重定向登录，后端用 Casdoor JWKS 验签 JWT，从 `roles` claim 解析角色做鉴权。

## 4. 工作目录结构（`mb-casd/`）

```
mb-casd/
├── docker-compose.yml          # casdoor + postgres 两个服务
├── .env.example                # 入库：变量清单与说明（不含真实密钥）
├── .env                        # 不入库：DB 密码、管理员初始密码等
├── conf/
│   └── app.conf                # 挂载到 /conf/app.conf
├── init_data/
│   └── init_data.json          # 挂载：组织 + 应用 + 证书 + RBAC + 管理员种子
├── assets/                     # 迈博 logo / favicon / 登录页自定义 CSS
│   ├── maibo-logo.png
│   └── favicon.ico
├── docs/
│   ├── apps/
│   │   └── mp-pm.md            # 应用接入档案（OIDC 配置 + 角色 + 权限矩阵 + 变更记录）
│   ├── decisions/
│   │   └── 0001-static-assets-cdn.md   # CDN/内网限制记录（ADR）
│   └── superpowers/specs/
│       └── 2026-06-28-mb-casd-iam-design.md   # 本文件
├── maibo-logo.jpg              # 原始 logo（已有）
└── README.md                   # 启动 / 初始化 / 接入说明
```

每接入一个新上层应用，在 `docs/apps/` 下新增同结构档案，RBAC 等变更记录在该文件的「变更记录」表中。

## 5. 组件设计

### 5.1 Postgres 服务

- 镜像：`postgres:16-alpine`
- 命名卷 `pgdata` 持久化；`healthcheck` 用 `pg_isready`
- 库名 `casdoor`；用户/密码来自 `.env`
- 仅本机暴露 `5432`（POC）

### 5.2 Casdoor 服务

- 镜像：`casbin/casdoor:<pinned>`（**钉死版本号**，不用 `latest`，保证可复现）。
  - 取舍：「用最新 release」与「与本地源码 `v3.100.0` 对齐」可能冲突。**决定**：实施时查 Docker Hub 最新稳定 release，若 ≥ `v3.100.0` 则钉死该最新版；否则钉死 `v3.100.0`。无论哪种都写死具体版本号，不用浮动 tag。
- `depends_on` 等 db 健康后启动
- 启动命令带 `--createDatabase=true`（首启自动建库）
- 挂载：`./conf:/conf/`、`./init_data/init_data.json:/init_data.json`、`./assets:/assets`（或经 staticBaseUrl 提供）
- 暴露 `8000`

### 5.3 `app.conf` 关键改动（基于仓库 `conf/app.conf`）

| 配置 | 值 | 说明 |
|---|---|---|
| `driverName` | `postgres` | |
| `dataSourceName` | `user=<u> password=<p> host=db port=5432 sslmode=disable dbname=` | dbname 留空以便建库 |
| `dbName` | `casdoor` | |
| `defaultLanguage` | `zh` | 默认中文 |
| `forceLanguage` | `zh` | **强制中文**，隐藏语言切换（D4） |
| `initDataFile` | `/init_data.json` | |
| `initDataNewOnly` | `true` | 已存在数据不覆盖，便于反复重启 |
| `staticBaseUrl` | 本地资源地址 | 内网取向；见 ADR-0001 |
| `showGithubCorner` | `false` | 去掉 GitHub 角标 |

> 实施时需对照预构建镜像验证 `runmode`/`origin`/前端静态目录相关字段的实际行为，确保挂载的 `app.conf` 与镜像内置前端服务方式一致。

### 5.4 `init_data.json`（数据初始化，定制核心）

- **组织 `mabpharm`**：`displayName=迈博药业`，`favicon`/`defaultAvatar` 指向迈博资源，`languages=["zh"]`，`passwordType=bcrypt`，`themeData` 取迈博品牌色（蓝 / 品红 / 绿，取自 logo）。
- **应用 `mp-pm`**：
  - 类型 OIDC；`enablePassword=true`；`enablePkce=true`
  - `grantTypes` 仅 `["authorization_code","refresh_token"]`（不放开 password/implicit）
  - `tokenFormat=JWT`
  - `redirectUris=["http://localhost:5175/callback"]`（mp-pm Vite 固定端口 5175）
  - `logo` 指向迈博资源
  - `cert` 引用 Casdoor 内置签名证书 `cert-built-in`（免手工生成密钥）
- **RBAC**：见第 7 节。
- **管理员种子用户**：一个 `isAdmin=true` 的 IAM 中台管理员，初始密码来自 `.env`，约定首登改密。

## 6. 品牌化（迈博 + 中文）

- **Logo / Favicon**：组织与应用的 `logo`、`favicon` 指向 `assets/` 下迈博资源。
- **主题色**：组织 `themeData` 配迈博品牌色。
- **登录页**：通过应用的自定义 CSS（注入）微调登录页，呈现迈博风格。
- **中文**：`forceLanguage=zh` + 组织 `languages=["zh"]`，全站中文、无语言切换。
- **去社区化**：`showGithubCorner=false`。

## 7. RBAC 设计

### 7.1 职责划分（D7，最小侵入 mp-pm）

- **Casdoor = 身份与角色的唯一来源**：负责登录、用户管理、角色分配，并在 token 中下发 `roles`。一个用户分配一个角色（匹配 mp-pm 现有单角色模型 `User.role`）。
- **mp-pm = 保留其代码内既有「角色→权限」矩阵**（`src/lib/permissions.ts`，20+ 条细粒度权限如 `project.create`）。接入改造仅把硬编码用户换成「从 token 的 `roles` 解析出的角色」，`can(role, perm)` 逻辑不变。
- **平台管理权限**（谁能进 Casdoor 管理台）由 Casdoor 用户 `isAdmin` 控制，独立于这 6 个业务角色。
- 后续可选项：把细粒度权限矩阵迁入 Casdoor 统一治理（见第 11 节），本期不做。

### 7.2 起步角色（mp-pm 真实角色，原样落 Casdoor 种子）

| Casdoor 角色名 | displayName | 主要权限（摘自权限矩阵） |
|---|---|---|
| `admin` | 系统管理员 | 系统配置、用户管理、全权 |
| `cmc_lead` | CMC 负责人 | 项目/模板增删改、全局视图、工作量 |
| `project_lead` | 项目负责人 | 子项目/任务/甘特维护、经理看板 |
| `rd` | 工艺开发 | 自有任务更新、个人看板、自有甘特 |
| `production` | 生产支持 | 自有任务更新、日历编辑 |
| `qa_qc` | QA/QC | 偏差审核、批次放行、数据导出 |

> 完整权限矩阵以 `docs/apps/mp-pm.md` 为准（单一变更跟踪源）。

### 7.3 Casbin 模型

- 标准 RBAC（`sub, obj, act` + 角色继承 `g`）。
- 本期 Casdoor 侧只用到「用户→角色」分配；细粒度 `obj/act` 判定在 mp-pm 内完成。

## 8. mp-pm OIDC 接入（D6，本期端到端）

### 8.1 现状

- 前端 Vite（端口 5175，`strictPort`），**当前无真实登录**：`src/store/auth.ts` 硬编码 CTO 用户（郭主任 / `cmc_lead`）。
- 后端 FastAPI，已用 `python-jose[cryptography]`，已有 `app.api.v1.auth` 模块，PostgreSQL/SQLAlchemy 栈。

### 8.2 前端改造

- 引入 OIDC 客户端（`oidc-client-ts`，授权码+PKCE；或 `casdoor-js-sdk`）。
- 新增 `/callback` 路由页处理回跳、存 token。
- 改 `src/store/auth.ts`：`currentUser` 改为从已验证 token 的 `roles` claim 解析出 `User`（含 `role`）；保留 `useAuth` 接口形态，使既有组件零改动。
- 未登录态重定向到 Casdoor `/login/oauth/authorize`。

### 8.3 后端改造

- 新增/改造鉴权中间件：用 Casdoor JWKS（`/.well-known/jwks`）验签 JWT（复用 `python-jose`）。
- 从已验证 claims 读取用户标识与 `roles`，映射到 mp-pm `Role`。
- 受保护接口依据角色鉴权。

### 8.4 角色 claim 映射

- Casdoor token 中的角色 → mp-pm `Role`（6 个角色名一一对应，命名刻意保持一致以免翻译层）。
- 单角色取值规则、claim 的确切字段名（`roles` 数组结构）需在 P4 用真实 token 核对后固化，并记入 `docs/apps/mp-pm.md`。

## 9. 静态资源 / 内网限制

用官方预构建镜像时，前端 build 仍有少量资源默认走 `cdn.casbin.org`。POC 联网无影响；完全内网/离线需改「源码构建」路线（后续）。详见 `docs/decisions/0001-static-assets-cdn.md`。

## 10. 分阶段交付与验证

| 阶段 | 内容 | 验证标准 |
|---|---|---|
| P1 | compose 起 postgres + casdoor，自动建库 | `docker compose up` 健康；访问 `:8000` 管理台；种子管理员登录成功 |
| P2 | 迈博品牌化（logo/favicon/主题色/中文/登录页） | 登录页与管理台呈现迈博品牌、全中文、无语言切换 |
| P3 | RBAC 种子（6 角色 + 模型 + 角色分配）+ 测试用户 | 不同角色测试用户可被正确识别 |
| P4 | mp-pm OIDC 端到端接入（前端+后端） | 真机走通「登录 → 回跳 → 按角色访问」；一条负向用例（无权角色被拒） |
| P5（后续，不在本期） | 生产加固：反代+TLS、密钥/备份、源码构建实现完全内网 | — |

## 11. 后续 / 未决项（非本期）

- P5 生产加固：反向代理 + TLS、密钥管理、Postgres 备份、资源限制、生产日志。
- 完全内网/离线：改源码构建，打自带迈博品牌 + 本地静态资源的镜像。
- 细粒度权限矩阵迁入 Casdoor 统一治理（届时 mp-pm 改为查询 Casdoor `/api/enforce`）。
- 多角色用户支持（若将来用户需要兼任多角色，需扩展 mp-pm 单角色模型）。

## 12. 安全注意

- 真实密钥只进 `.env`（不入库）；仓库放 `.env.example`。
- 管理员/测试用户初始密码弱口令仅限本机 POC，约定首登改密；进入任何联网环境前必须更换。
- `sslmode=disable` 仅限本机 POC；生产启用 TLS。

## 13. 验收口径（本期完成的定义）

- `docker compose up` 一条命令起全栈，Casdoor 管理台中文、迈博品牌。
- Casdoor 内已注册 mp-pm 应用、6 个角色、若干测试用户。
- 从 mp-pm 真机走通端到端登录闭环，按角色看到/被拒相应功能。
- `docs/apps/mp-pm.md`、`docs/decisions/0001-static-assets-cdn.md`、`README.md` 齐备。
