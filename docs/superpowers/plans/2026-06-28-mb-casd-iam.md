# 迈博药业 IAM 中台（mb-casd）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本机 docker 跑通迈博品牌化的 Casdoor IAM 中台（Postgres 后端），并让试点应用 mp-pm 通过 OIDC 授权码+PKCE 完成端到端登录与 RBAC 鉴权。

**Architecture:** 官方 `casbin/casdoor` 镜像（不改源码）+ `postgres:16-alpine`，经 docker-compose 编排；定制全部收敛在挂载的 `conf/app.conf`、`init_data/init_data.json`、`assets/`。mp-pm 前端用 `oidc-client-ts` 重定向到 Casdoor 登录，拿 access_token；mp-pm 后端（FastAPI）用 Casdoor JWKS 验签该 token，按 username 关联本地 User、按 token 中的角色做 RBAC。

**Tech Stack:** Docker Compose、Casdoor、PostgreSQL 16、FastAPI、python-jose[cryptography]、React + Vite + TypeScript、oidc-client-ts、axios。

## Global Constraints

逐条适用于每个任务（值均为最终值，照抄）：

- **端口分配（务必避免冲突）：** Casdoor = `8000`；mp-pm 后端 = `8080`（用 `PORT=8080` 启动，原默认 8000 与 Casdoor 冲突）；mp-pm 前端 = `5175`（Vite `strictPort`）。
- **镜像钉死具体版本号，禁用 `latest`。** 实施 Task 1 时查 Docker Hub 最新稳定 release：若 ≥ `v3.100.0` 则钉该版，否则钉 `v3.100.0`。下文以 `${CASDOOR_TAG}` 指代，首次确定后全程写死同一值。
- **仅中文：** `app.conf` 设 `forceLanguage = "zh"`；mabpharm 组织 `languages = ["zh"]`。
- **密钥只进 `.env`（已 gitignore），仓库放 `.env.example`。** 禁止提交真实凭证。
- **6 个角色名（与 mp-pm 代码一致，禁止改名）：** `admin`、`cmc_lead`、`project_lead`、`rd`、`production`、`qa_qc`。
- **Casdoor 用户名必须与 mp-pm 本地 DB 用户名一致**（后端按 username 关联），见 Task 4 用户清单。
- **`sslmode=disable` 与弱口令仅限本机 POC**；任何联网环境前必须更换。
- mp-pm 改造遵循其既有风格：axios 客户端 + `setToken`、Zustand store、FastAPI 依赖注入；`src/lib/permissions.ts` 的 `can()` 矩阵不动。

---

## File Structure

**mb-casd 仓库（新建）：**
- `docker-compose.yml` — 编排 casdoor + postgres
- `.env.example` — 变量清单（入库）；`.env` — 真实值（不入库）
- `conf/app.conf` — Casdoor 配置（Postgres / 中文 / 初始化文件 / 静态资源）
- `init_data/init_data.json` — 组织 + 应用 + 角色 + 测试用户种子
- `assets/maibo-logo.png`、`assets/favicon.ico` — 品牌资源
- `README.md` — 启动 / 初始化 / 接入说明
- `docs/apps/mp-pm.md` — 接入档案（回填真实 clientId、确认角色 claim）

**mp-pm 仓库（前端，修改/新建）：**
- `src/lib/oidc.ts`（新建）— `oidc-client-ts` UserManager 配置
- `src/pages/Callback.tsx`（新建）— 回调页
- `src/App.tsx`（修改）— 加 `/callback` 路由 + 未登录守卫
- `src/store/auth.ts`（修改）— currentUser 由 `/auth/me` 派生
- `src/data/bootstrap.ts`（修改）— 用 Casdoor token 替代后端 login
- `src/api/client.ts`（修改）— baseURL 默认改 `:8080`
- `package.json`（修改）— 加 `oidc-client-ts`
- `.env.example` / `.env`（修改）— 加 `VITE_*` OIDC 配置

**mp-pm 仓库（后端，修改/新建）：**
- `backend/app/core/config.py`（修改）— 加 Casdoor 设置
- `backend/app/core/casdoor.py`（新建）— JWKS 拉取 + RS256 验签 + 取角色
- `backend/app/api/deps.py`（修改）— `get_current_user` 走 Casdoor 验签 + username 关联
- `backend/tests/test_casdoor_auth.py`（新建）— 验签单测
- `backend/.env.example`（修改）— 加 Casdoor 变量

---

## Task 1: Casdoor + Postgres 起栈（P1）

**Files:**
- Create: `/Users/hele/Projects/openlims/mb-casd/.env.example`
- Create: `/Users/hele/Projects/openlims/mb-casd/.env`（本地，不入库）
- Create: `/Users/hele/Projects/openlims/mb-casd/docker-compose.yml`
- Create: `/Users/hele/Projects/openlims/mb-casd/conf/app.conf`

**Interfaces:**
- Produces: 运行中的 Casdoor（`http://localhost:8000`）+ Postgres（`localhost:5432`，库 `casdoor`）；后续任务挂载 `init_data/` 与 `assets/`。

- [ ] **Step 1: 写 `.env.example`（入库）**

```dotenv
# Postgres
POSTGRES_USER=casdoor
POSTGRES_PASSWORD=change-me-strong
POSTGRES_DB=casdoor
# Casdoor 镜像版本（Task 1 确定后写死具体号，禁用 latest）
CASDOOR_TAG=v3.100.0
```

- [ ] **Step 2: 复制为 `.env` 并填本机值**

Run:
```bash
cd /Users/hele/Projects/openlims/mb-casd && cp .env.example .env
```
然后把 `POSTGRES_PASSWORD` 改成本机强口令；`CASDOOR_TAG` 按 Global Constraints 确认后写死。

- [ ] **Step 3: 写 `conf/app.conf`**

```ini
appname = casdoor
httpport = 8000
runmode = prod
copyrequestbody = true
driverName = postgres
dataSourceName = "user=${POSTGRES_USER} password=${POSTGRES_PASSWORD} host=db port=5432 sslmode=disable dbname="
dbName = casdoor
tableNamePrefix =
showSql = false
redisEndpoint =
defaultStorageProvider =
isCloudIntranet = false
authState = "casdoor"
verificationCodeTimeout = 10
initScore = 0
logPostOnly = true
isUsernameLowered = false
origin = "http://localhost:8000"
originFrontend =
staticBaseUrl = "https://cdn.casbin.org"
isDemoMode = false
batchSize = 100
showGithubCorner = false
forceLanguage = "zh"
defaultLanguage = "zh"
defaultApplication = "app-built-in"
maxItemsForFlatMenu = 7
enableErrorMask = false
enableGzip = true
ldapServerPort = 389
radiusServerPort = 1812
radiusDefaultOrganization = "built-in"
radiusSecret = "secret"
quota = {"organization": -1, "user": -1, "application": -1, "provider": -1}
logConfig = {"adapter":"file", "filename": "logs/casdoor.log", "maxdays":99999, "perm":"0770"}
initDataNewOnly = true
initDataFile = "/init_data.json"
```

> 注意：`dataSourceName` 末尾 `dbname=` 留空，Casdoor 会把 `dbName` 值（`casdoor`）追加上去；`host=db` 指向 compose 服务名。`${...}` 由下一步 compose 的 env 注入（Casdoor 支持读取 app.conf 中环境变量占位）。若该版本镜像不展开占位符，则在本步把 `${POSTGRES_USER}`/`${POSTGRES_PASSWORD}` 直接替换为 `.env` 里的真实值（此时 `conf/app.conf` 不入库，改入 `.gitignore`）。

- [ ] **Step 4: 写 `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10

  casdoor:
    image: casbin/casdoor:${CASDOOR_TAG}
    restart: unless-stopped
    command: ["--createDatabase=true"]
    depends_on:
      db:
        condition: service_healthy
    environment:
      RUNNING_IN_DOCKER: "true"
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "8000:8000"
    volumes:
      - ./conf/app.conf:/conf/app.conf
      - ./init_data/init_data.json:/init_data.json
      - ./assets:/files          # Casdoor 经 /files 路由提供该目录（main.go: SetStaticPath("/files","files")）

volumes:
  pgdata:
```

> Task 1 阶段 `init_data/init_data.json` 与 `assets/` 尚未创建。先创建占位：`mkdir -p assets init_data && echo '{}' > init_data/init_data.json`，避免 compose 挂载报错（空 `{}` 不影响 Casdoor 默认初始化）。

- [ ] **Step 5: 起栈**

Run:
```bash
cd /Users/hele/Projects/openlims/mb-casd && mkdir -p assets init_data && printf '{}\n' > init_data/init_data.json && docker compose up -d
```
Expected: 拉取镜像后 `db` 与 `casdoor` 两个容器 `Up`；`docker compose ps` 中 db 为 `healthy`。

- [ ] **Step 6: 验证 Casdoor 可访问 + 建表成功**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/ ; \
docker compose exec db psql -U "$POSTGRES_USER" -d casdoor -c "\dt" | grep -i user
```
Expected: 首条返回 `200`；第二条能列出 Casdoor 的 `user` 等表（说明已自动建库建表）。

- [ ] **Step 7: 验证内置管理员登录**

浏览器开 `http://localhost:8000`，用内置 `admin` / `123` 登录管理台成功（POC 默认口令，后续 Task 2 提示更换）。

- [ ] **Step 8: 提交**

```bash
cd /Users/hele/Projects/openlims/mb-casd
git add .env.example docker-compose.yml conf/app.conf
git commit -m "feat: 起 Casdoor + Postgres 本机栈（P1）"
```

---

## Task 2: 迈博品牌化 + 中文 + 组织种子（P2）

**Files:**
- Create: `/Users/hele/Projects/openlims/mb-casd/assets/maibo-logo.png`
- Create: `/Users/hele/Projects/openlims/mb-casd/assets/favicon.ico`
- Modify: `/Users/hele/Projects/openlims/mb-casd/init_data/init_data.json`

**Interfaces:**
- Consumes: Task 1 的运行栈。
- Produces: 组织 `mabpharm`（迈博品牌、中文）。

- [ ] **Step 1: 生成品牌资源**

Run（从已有 logo 派生 PNG 与 favicon；需要 ImageMagick，没有则用任意工具手动导出同名文件）：
```bash
cd /Users/hele/Projects/openlims/mb-casd
magick maibo-logo.jpg -resize 200x200 assets/maibo-logo.png
magick maibo-logo.jpg -resize 64x64 assets/favicon.ico
```
Expected: `assets/maibo-logo.png` 与 `assets/favicon.ico` 存在。

- [ ] **Step 2: 写 `init_data/init_data.json` 的组织段**

把占位 `{}` 替换为下列内容（以 casdoor 模板 `/Users/hele/Projects/casdoor/init_data.json.template` 的字段结构为基准，其余未列字段留空/默认）：

```json
{
  "organizations": [
    {
      "owner": "admin",
      "name": "mabpharm",
      "displayName": "迈博药业",
      "websiteUrl": "https://www.mabpharm.com",
      "favicon": "http://localhost:8000/files/favicon.ico",
      "passwordType": "bcrypt",
      "passwordOptions": ["AtLeast6"],
      "countryCodes": ["CN"],
      "defaultAvatar": "http://localhost:8000/files/maibo-logo.png",
      "languages": ["zh"],
      "tags": [],
      "masterPassword": "",
      "defaultPassword": "",
      "enableSoftDeletion": false,
      "isProfilePublic": false,
      "themeData": {
        "themeType": "default",
        "colorPrimary": "#1a4f9c",
        "borderRadius": 6,
        "isCompact": false
      }
    }
  ]
}
```

> `colorPrimary` 取 logo 主蓝；如需更贴近品牌，可在管理台「组织 → 主题」里微调后导出回填。

- [ ] **Step 3: 重启并重新初始化**

Run:
```bash
cd /Users/hele/Projects/openlims/mb-casd && docker compose restart casdoor && sleep 5 && docker compose logs --tail=30 casdoor | grep -i "init\|data"
```
Expected: 日志显示读取了 `/init_data.json`，无报错。

- [ ] **Step 4: 验证品牌资源可达 + 中文**

Run（确认 `/files` 路由确实提供了挂载的资源）：
```bash
curl -s -o /dev/null -w "logo=%{http_code}\n" http://localhost:8000/files/maibo-logo.png
```
Expected: `logo=200`。
再开浏览器 `http://localhost:8000`：管理台为**中文**、右上角**无 GitHub 角标**；进入「组织」能看到 `mabpharm / 迈博药业`，主题色为迈博蓝、favicon 为迈博。

- [ ] **Step 5: 更换内置管理员口令（POC 安全基线）**

在管理台把内置 `admin` 用户口令从 `123` 改为强口令（仅本机也应改），记到本机密码管理处，不入库。

- [ ] **Step 6: 提交**

```bash
cd /Users/hele/Projects/openlims/mb-casd
git add assets/maibo-logo.png assets/favicon.ico init_data/init_data.json
git commit -m "feat: 迈博品牌化 + 中文 + mabpharm 组织种子（P2）"
```

---

## Task 3: mp-pm OIDC 应用种子（P3a）

**Files:**
- Modify: `/Users/hele/Projects/openlims/mb-casd/init_data/init_data.json`
- Modify: `/Users/hele/Projects/openlims/mb-casd/docs/apps/mp-pm.md`

**Interfaces:**
- Consumes: 组织 `mabpharm`。
- Produces: OIDC 应用 `mp-pm`（clientId/secret 由 Casdoor 生成）；后续 mp-pm 前后端消费其 OIDC 端点与 JWKS。

- [ ] **Step 1: 在 `init_data.json` 顶层加 `applications` 段**

```json
  "applications": [
    {
      "owner": "admin",
      "name": "mp-pm",
      "displayName": "CMC 项目管理系统",
      "logo": "http://localhost:8000/files/maibo-logo.png",
      "homepageUrl": "http://localhost:5175",
      "organization": "mabpharm",
      "cert": "cert-built-in",
      "enablePassword": true,
      "enableSignUp": false,
      "clientId": "mppm-client-id-0001",
      "clientSecret": "mppm-client-secret-0001-change-me",
      "enablePkce": true,
      "grantTypes": ["authorization_code", "refresh_token"],
      "redirectUris": ["http://localhost:5175/callback"],
      "tokenFormat": "JWT",
      "tokenFields": [],
      "expireInHours": 168,
      "signinMethods": [
        { "name": "Password", "displayName": "Password", "rule": "All" }
      ]
    }
  ]
```

> `clientId`/`clientSecret` 这里预设固定值便于本机联调；Casdoor 也可自动生成——以管理台「应用 → mp-pm」实际显示为准，并在 Step 4 回填文档与各 `.env`。`cert-built-in` 为 Casdoor 内置签名证书；若该版本未自带，则在管理台「证书」新建一个 RSA 证书并把 `cert` 改为其名。

- [ ] **Step 2: 重启**

Run:
```bash
cd /Users/hele/Projects/openlims/mb-casd && docker compose restart casdoor && sleep 5
```

- [ ] **Step 3: 验证应用与 OIDC 端点可达**

Run:
```bash
curl -s http://localhost:8000/.well-known/openid-configuration | python3 -m json.tool | grep -E "authorization_endpoint|token_endpoint|jwks_uri|issuer"
curl -s http://localhost:8000/.well-known/jwks | python3 -m json.tool | grep -E "kid|kty"
```
Expected: discovery 返回 `issuer=http://localhost:8000`、authorize/token/jwks 端点；JWKS 返回至少一个含 `kid`、`kty=RSA` 的 key。管理台「应用」中存在 `mp-pm`。

- [ ] **Step 4: 回填 `docs/apps/mp-pm.md`**

把第 1 节表格中的 `clientId / clientSecret` 改为管理台实际值；勾掉「OIDC 客户端配置」相关项；在「变更记录」加一行（日期 2026-06-28，应用已注册）。

- [ ] **Step 5: 提交**

```bash
cd /Users/hele/Projects/openlims/mb-casd
git add init_data/init_data.json docs/apps/mp-pm.md
git commit -m "feat: 注册 mp-pm OIDC 应用（P3a）"
```

---

## Task 4: RBAC 角色 + 测试用户种子（P3b）

**Files:**
- Modify: `/Users/hele/Projects/openlims/mb-casd/init_data/init_data.json`

**Interfaces:**
- Consumes: 组织 `mabpharm`、应用 `mp-pm`。
- Produces: 6 个角色 + 6 个测试用户（用户名与 mp-pm 本地 DB 一致），每人一个角色。

- [ ] **Step 1: 在 `init_data.json` 顶层加 `roles` 段（6 个角色）**

```json
  "roles": [
    { "owner": "mabpharm", "name": "admin",        "displayName": "系统管理员",   "users": ["mabpharm/admin"],     "roles": [], "isEnabled": true },
    { "owner": "mabpharm", "name": "cmc_lead",     "displayName": "CMC 负责人",   "users": ["mabpharm/guo.cmc"],   "roles": [], "isEnabled": true },
    { "owner": "mabpharm", "name": "project_lead", "displayName": "项目负责人",   "users": ["mabpharm/li.pm1"],    "roles": [], "isEnabled": true },
    { "owner": "mabpharm", "name": "rd",           "displayName": "工艺开发",     "users": ["mabpharm/liu.usp1"],  "roles": [], "isEnabled": true },
    { "owner": "mabpharm", "name": "production",   "displayName": "生产支持",     "users": ["mabpharm/mao.prod1"], "roles": [], "isEnabled": true },
    { "owner": "mabpharm", "name": "qa_qc",        "displayName": "QA/QC",       "users": ["mabpharm/qa.zhao"],   "roles": [], "isEnabled": true }
  ]
```

- [ ] **Step 2: 在 `init_data.json` 顶层加 `users` 段（6 个测试用户，用户名对齐 mp-pm 本地 DB）**

```json
  "users": [
    { "owner": "mabpharm", "name": "admin",     "type": "normal-user", "password": "Maibo@2026", "displayName": "张管理", "email": "admin@mabpharm.com",     "isAdmin": true,  "signupApplication": "mp-pm" },
    { "owner": "mabpharm", "name": "guo.cmc",   "type": "normal-user", "password": "Maibo@2026", "displayName": "郭主任", "email": "guo.cmc@mabpharm.com",   "isAdmin": false, "signupApplication": "mp-pm" },
    { "owner": "mabpharm", "name": "li.pm1",    "type": "normal-user", "password": "Maibo@2026", "displayName": "李项目", "email": "li.pm1@mabpharm.com",    "isAdmin": false, "signupApplication": "mp-pm" },
    { "owner": "mabpharm", "name": "liu.usp1",  "type": "normal-user", "password": "Maibo@2026", "displayName": "刘上游", "email": "liu.usp1@mabpharm.com",  "isAdmin": false, "signupApplication": "mp-pm" },
    { "owner": "mabpharm", "name": "mao.prod1", "type": "normal-user", "password": "Maibo@2026", "displayName": "毛生产", "email": "mao.prod1@mabpharm.com", "isAdmin": false, "signupApplication": "mp-pm" },
    { "owner": "mabpharm", "name": "qa.zhao",   "type": "normal-user", "password": "Maibo@2026", "displayName": "赵质量", "email": "qa.zhao@mabpharm.com",   "isAdmin": false, "signupApplication": "mp-pm" }
  ]
```

> 这 6 个用户名均取自 mp-pm 后端种子（`backend/app/seed/seed.json`），保证后端可按 username 关联到本地 User 行。弱口令 `Maibo@2026` 仅限本机 POC，约定首登改密。

- [ ] **Step 3: 重启并重新初始化**

Run:
```bash
cd /Users/hele/Projects/openlims/mb-casd && docker compose restart casdoor && sleep 5
```

- [ ] **Step 4: 验证角色与用户**

管理台「角色」可见 6 个角色；「用户」可见 6 个测试用户，各自 `Roles` 列显示对应角色（例如 `guo.cmc` → `cmc_lead`）。

- [ ] **Step 5: 验证一个用户能登录 Casdoor 托管登录页**

浏览器开 `http://localhost:8000/login/oauth/authorize?client_id=<mp-pm clientId>&response_type=code&redirect_uri=http://localhost:5175/callback&scope=openid%20profile&state=test`，用 `guo.cmc / Maibo@2026` 登录，应跳到 `http://localhost:5175/callback?code=...`（此刻前端未起，浏览器显示连接失败属正常，关键是 URL 带回了 `code`）。

- [ ] **Step 6: 提交**

```bash
cd /Users/hele/Projects/openlims/mb-casd
git add init_data/init_data.json
git commit -m "feat: RBAC 6 角色 + 测试用户种子（P3b）"
```

---

## Task 5: mp-pm 前端 OIDC 登录（P4a）

**Files:**
- Modify: `/Users/hele/Projects/openlims/mp-pm/package.json`（加 `oidc-client-ts`）
- Create: `/Users/hele/Projects/openlims/mp-pm/src/lib/oidc.ts`
- Create: `/Users/hele/Projects/openlims/mp-pm/src/pages/Callback.tsx`
- Modify: `/Users/hele/Projects/openlims/mp-pm/src/App.tsx`
- Modify: `/Users/hele/Projects/openlims/mp-pm/src/store/auth.ts`
- Modify: `/Users/hele/Projects/openlims/mp-pm/src/data/bootstrap.ts`
- Modify: `/Users/hele/Projects/openlims/mp-pm/src/api/client.ts`
- Modify: `/Users/hele/Projects/openlims/mp-pm/.env.example`

**Interfaces:**
- Consumes: Casdoor OIDC 端点（Task 3）、测试用户（Task 4）、后端 `/auth/me`（Task 6 提供 Casdoor 验签；本任务先用前端解析 token 兜底，联调在 Task 7）。
- Produces: 前端登录态：`useAuth().currentUser`（含 `role`），axios 携带 Casdoor access_token。

- [ ] **Step 1: 安装依赖**

Run:
```bash
cd /Users/hele/Projects/openlims/mp-pm && npm install oidc-client-ts@3
```
Expected: `package.json` 出现 `oidc-client-ts`。

- [ ] **Step 2: 写 `.env.example` 的 OIDC 段**

追加：
```dotenv
VITE_USE_API=true
VITE_API_URL=http://localhost:8080/api/v1
VITE_OIDC_AUTHORITY=http://localhost:8000
VITE_OIDC_CLIENT_ID=mppm-client-id-0001
VITE_OIDC_REDIRECT_URI=http://localhost:5175/callback
```
然后 `cp .env.example .env`（若已存在 `.env` 则手动并入）。`VITE_OIDC_CLIENT_ID` 用 Task 3 的实际 clientId。

- [ ] **Step 3: 写 `src/lib/oidc.ts`**

```typescript
import { UserManager, WebStorageStateStore, type User as OidcUser } from 'oidc-client-ts'

const authority = import.meta.env.VITE_OIDC_AUTHORITY as string
const client_id = import.meta.env.VITE_OIDC_CLIENT_ID as string
const redirect_uri = import.meta.env.VITE_OIDC_REDIRECT_URI as string

export const userManager = new UserManager({
  authority,
  client_id,
  redirect_uri,
  response_type: 'code',
  scope: 'openid profile email',
  // Casdoor 端点（discovery 也可，但显式声明更稳）
  metadata: {
    issuer: authority,
    authorization_endpoint: `${authority}/login/oauth/authorize`,
    token_endpoint: `${authority}/api/login/oauth/access_token`,
    jwks_uri: `${authority}/.well-known/jwks`,
    userinfo_endpoint: `${authority}/api/userinfo`,
  },
  userStore: new WebStorageStateStore({ store: window.localStorage }),
})

export function login(): Promise<void> {
  return userManager.signinRedirect()
}

export async function getAccessToken(): Promise<string | null> {
  const u = await userManager.getUser()
  return u && !u.expired ? u.access_token : null
}

export async function completeLogin(): Promise<OidcUser> {
  return userManager.signinRedirectCallback()
}
```

- [ ] **Step 4: 写 `src/pages/Callback.tsx`**

```tsx
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { completeLogin } from '../lib/oidc'

export default function Callback() {
  const navigate = useNavigate()
  useEffect(() => {
    completeLogin()
      .then(() => navigate('/', { replace: true }))
      .catch(() => navigate('/', { replace: true }))
  }, [navigate])
  return (
    <div className="h-full flex items-center justify-center gap-2 text-sm text-ink-500">
      <Loader2 className="w-4 h-4 animate-spin" /> 登录中 …
    </div>
  )
}
```

- [ ] **Step 5: 改 `src/api/client.ts` 默认 baseURL 到 8080**

把
```typescript
const baseURL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000/api/v1'
```
改为
```typescript
const baseURL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8080/api/v1'
```

- [ ] **Step 6: 改 `src/store/auth.ts` 由后端 `/auth/me` 派生用户**

整体替换为：
```typescript
// 认证 store —— 由 Casdoor 登录态派生当前用户。
import { create } from 'zustand'
import type { User } from '../types'
import { users as mockUsers } from '../mock/users'

interface AuthState {
  currentUser: User            // 保持非空，既有组件直接读 currentUser.role 不受影响
  setCurrentUser: (u: User) => void
}

export const useAuth = create<AuthState>((set) => ({
  // 兜底：未登录前用首个 mock 用户占位（App.tsx 守卫会在无 token 时跳登录，主界面不会真正渲染）。
  currentUser: mockUsers[0],
  setCurrentUser: (u) => set({ currentUser: u }),
}))
```

- [ ] **Step 7: 改 `src/data/bootstrap.ts` 用 Casdoor token**

定位现有「以 CTO 身份登录后端拿 JWT」的逻辑（`authApi.login` / `CTO_USERNAME`），替换为：先拿 Casdoor token 注入 axios，再调 `/auth/me` 拿当前用户写入 auth store，再继续既有数据拉取。把对应片段改为：
```typescript
import { getAccessToken } from '../lib/oidc'
import { setToken } from '../api/client'
import { api } from '../api/client'
import { useAuth } from '../store/auth'
// ... 在 bootstrap() 内、拉取数据之前：
const token = await getAccessToken()
if (token) {
  setToken(token)
  const me = await api.get('/auth/me')   // 后端用 Casdoor JWKS 验签（Task 6）
  useAuth.getState().setCurrentUser(me.data as User)
}
```
> 删除原先调用后端 `/auth/login`（`guo.cmc`）发 JWT 的逻辑——登录改由 Casdoor 负责。

- [ ] **Step 8: 改 `src/App.tsx` 加 `/callback` 路由与未登录守卫**

在 `import` 区加 `import Callback from './pages/Callback'` 与 `import { getAccessToken, login } from './lib/oidc'`。在 `<Routes>` 内、`AppLayout` 包裹之外加：
```tsx
<Route path="/callback" element={<Callback />} />
```
并在 `App()` 顶部加一次性登录守卫（无 token 则跳 Casdoor）：
```tsx
useEffect(() => {
  if (window.location.pathname === '/callback') return
  getAccessToken().then((t) => { if (!t) login() })
}, [])
```

- [ ] **Step 9: 起前端验证重定向闭环（需 Casdoor 在跑）**

Run:
```bash
cd /Users/hele/Projects/openlims/mp-pm && npm run dev
```
浏览器开 `http://localhost:5175`：应被重定向到 Casdoor 登录页；用 `guo.cmc / Maibo@2026` 登录后回跳 `http://localhost:5175/callback` 再进首页。打开 DevTools → Application → Local Storage，应存有 `oidc.user:...` 含 `access_token`。
Expected: 能登录并回到首页（此刻 `/auth/me` 可能 401，因后端验签在 Task 6；本步只验证「重定向 + 拿到 token」闭环）。

- [ ] **Step 10: 提交（在 mp-pm 仓库）**

```bash
cd /Users/hele/Projects/openlims/mp-pm
git add package.json package-lock.json src/lib/oidc.ts src/pages/Callback.tsx src/App.tsx src/store/auth.ts src/data/bootstrap.ts src/api/client.ts .env.example
git commit -m "feat(auth): 接入 Casdoor OIDC 登录（前端）"
```

---

## Task 6: mp-pm 后端 Casdoor JWKS 验签（P4b）

**Files:**
- Modify: `/Users/hele/Projects/openlims/mp-pm/backend/app/core/config.py`
- Create: `/Users/hele/Projects/openlims/mp-pm/backend/app/core/casdoor.py`
- Modify: `/Users/hele/Projects/openlims/mp-pm/backend/app/api/deps.py`
- Create: `/Users/hele/Projects/openlims/mp-pm/backend/tests/test_casdoor_auth.py`
- Modify: `/Users/hele/Projects/openlims/mp-pm/backend/.env.example`

**Interfaces:**
- Consumes: Casdoor JWKS（`/.well-known/jwks`）、Task 5 前端发来的 `Authorization: Bearer <casdoor access_token>`。
- Produces:
  - `app.core.casdoor.verify_casdoor_token(token: str) -> dict` — 验签通过返回 claims，失败抛 `ValueError`。
  - `app.core.casdoor.extract_role(claims: dict) -> str | None` — 从 claims 取角色名（6 个之一）。
  - 改造后的 `get_current_user`：Bearer 走 Casdoor 验签 + 按 `preferred_username`/`name` 关联本地 `User`，并用 token 角色覆盖 `user.role`；保留 `DemoUser` 测试旁路。

- [ ] **Step 1: 写 `backend/app/core/config.py` 的 Casdoor 设置**

在 `Settings` 内（JWT 段附近）追加：
```python
    # —— Casdoor OIDC —— #
    CASDOOR_ENDPOINT: str = "http://localhost:8000"
    CASDOOR_CLIENT_ID: str = "mppm-client-id-0001"
    CASDOOR_ORG: str = "mabpharm"

    @property
    def casdoor_jwks_url(self) -> str:
        return f"{self.CASDOOR_ENDPOINT}/.well-known/jwks"
```

- [ ] **Step 2: 写 `backend/.env.example` 的 Casdoor 段**

追加：
```dotenv
CASDOOR_ENDPOINT=http://localhost:8000
CASDOOR_CLIENT_ID=mppm-client-id-0001
CASDOOR_ORG=mabpharm
```

- [ ] **Step 3: 写失败测试 `backend/tests/test_casdoor_auth.py`**

```python
"""Casdoor JWKS 验签 + 角色提取单测（自签 RSA，不依赖在跑的 Casdoor）。"""
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt, jwk

from app.core import casdoor
from app.core.config import settings

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-kid-1"


def _private_pem() -> str:
    return _KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _jwks() -> dict:
    pub_pem = _KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    k = jwk.construct(pub_pem, "RS256").to_dict()
    k["kid"] = _KID
    return {"keys": [k]}


def _make_token(claims: dict) -> str:
    headers = {"kid": _KID}
    return jwt.encode(claims, _private_pem(), algorithm="RS256", headers=headers)


def test_verify_valid_token(monkeypatch):
    monkeypatch.setattr(casdoor, "_fetch_jwks", lambda: _jwks())
    token = _make_token({
        "sub": "u-guo",
        "name": "guo.cmc",
        "preferred_username": "guo.cmc",
        "aud": settings.CASDOOR_CLIENT_ID,
        "iss": settings.CASDOOR_ENDPOINT,
        "roles": [{"owner": "mabpharm", "name": "cmc_lead"}],
    })
    claims = casdoor.verify_casdoor_token(token)
    assert claims["preferred_username"] == "guo.cmc"
    assert casdoor.extract_role(claims) == "cmc_lead"


def test_reject_bad_signature(monkeypatch):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    monkeypatch.setattr(casdoor, "_fetch_jwks", lambda: _jwks())
    bad = jwt.encode({"sub": "x", "aud": settings.CASDOOR_CLIENT_ID, "iss": settings.CASDOOR_ENDPOINT},
                     other_pem, algorithm="RS256", headers={"kid": _KID})
    try:
        casdoor.verify_casdoor_token(bad)
        assert False, "应当因签名不匹配而抛错"
    except ValueError:
        pass


def test_extract_role_variants():
    assert casdoor.extract_role({"roles": [{"name": "qa_qc"}]}) == "qa_qc"
    assert casdoor.extract_role({"roles": ["rd"]}) == "rd"
    assert casdoor.extract_role({"role": "admin"}) == "admin"
    assert casdoor.extract_role({"roles": []}) is None
```

- [ ] **Step 4: 跑测试确认失败**

Run:
```bash
cd /Users/hele/Projects/openlims/mp-pm/backend && PORT=8080 .venv/bin/python -m pytest tests/test_casdoor_auth.py -v
```
Expected: 因 `app.core.casdoor` 不存在而 `ImportError` / 全部失败。

- [ ] **Step 5: 写实现 `backend/app/core/casdoor.py`**

```python
"""Casdoor access_token（RS256/JWKS）验签 + 角色提取。

JWKS 用标准库 urllib 拉取并进程内缓存（运行时不引入新依赖）；
验签用 python-jose（已含 cryptography）。
"""
import json
import urllib.request
from typing import Any

from jose import jwt
from jose.exceptions import JWTError

from app.core.config import settings

_ROLES = {"admin", "cmc_lead", "project_lead", "rd", "production", "qa_qc"}
_jwks_cache: dict | None = None


def _fetch_jwks() -> dict:
    with urllib.request.urlopen(settings.casdoor_jwks_url, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _get_jwks(force: bool = False) -> dict:
    global _jwks_cache
    if _jwks_cache is None or force:
        _jwks_cache = _fetch_jwks()
    return _jwks_cache


def verify_casdoor_token(token: str) -> dict[str, Any]:
    """验签并返回 claims；失败抛 ValueError。kid 未命中时刷新一次 JWKS。"""
    for force in (False, True):
        jwks = _get_jwks(force=force)
        try:
            return jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=settings.CASDOOR_CLIENT_ID,
                issuer=settings.CASDOOR_ENDPOINT,
                options={"verify_at_hash": False},
            )
        except JWTError as e:
            last = e
            continue
    raise ValueError(f"Casdoor token 验签失败: {last}")


def extract_role(claims: dict[str, Any]) -> str | None:
    """从 claims 取出 6 个角色名之一。兼容 roles=[{name}]、roles=[str]、role=str。"""
    roles = claims.get("roles")
    if isinstance(roles, list):
        for r in roles:
            name = r.get("name") if isinstance(r, dict) else r
            if name in _ROLES:
                return name
    role = claims.get("role")
    if role in _ROLES:
        return role
    return None
```

- [ ] **Step 6: 跑测试确认通过**

Run:
```bash
cd /Users/hele/Projects/openlims/mp-pm/backend && PORT=8080 .venv/bin/python -m pytest tests/test_casdoor_auth.py -v
```
Expected: 3 个用例全部 PASS。

- [ ] **Step 7: 改 `backend/app/api/deps.py` 让 Bearer 走 Casdoor 验签**

把 `_resolve_demo_or_jwt` 中 `Bearer` 分支（`token = ...` 起至 `return user`）替换为：
```python
    token = authorization.removeprefix("Bearer ").strip()
    from app.core.casdoor import verify_casdoor_token, extract_role
    try:
        claims = verify_casdoor_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    username = claims.get("preferred_username") or claims.get("name")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing username")

    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"user {username!r} not provisioned")

    role = extract_role(claims)
    if role:
        user.role = role  # Casdoor 为角色唯一来源（仅本请求内覆盖，不落库）
    return user
```
> 保留文件顶部既有 import 与 `DemoUser` 分支不动。`decode_access_token` 不再用于 Bearer，可保留供其他用途。

- [ ] **Step 8: 跑后端全量测试确认无回归**

Run:
```bash
cd /Users/hele/Projects/openlims/mp-pm/backend && PORT=8080 .venv/bin/python -m pytest -q
```
Expected: 全绿（既有用例用 `DemoUser` 旁路，不受影响）。

- [ ] **Step 9: 提交（在 mp-pm 仓库）**

```bash
cd /Users/hele/Projects/openlims/mp-pm
git add backend/app/core/config.py backend/app/core/casdoor.py backend/app/api/deps.py backend/tests/test_casdoor_auth.py backend/.env.example
git commit -m "feat(auth): 后端用 Casdoor JWKS 验签 access_token"
```

---

## Task 7: 端到端联调 + 负向 RBAC + 文档（P4c）

**Files:**
- Modify: `/Users/hele/Projects/openlims/mb-casd/docs/apps/mp-pm.md`
- Create: `/Users/hele/Projects/openlims/mb-casd/README.md`

**Interfaces:**
- Consumes: Task 1–6 全部产物。
- Produces: 可演示的端到端登录闭环 + 验收记录。

- [ ] **Step 1: 三件套同时起**

Run（三个终端）：
```bash
# 1) Casdoor + Postgres
cd /Users/hele/Projects/openlims/mb-casd && docker compose up -d
# 2) mp-pm 后端（8080，Postgres 或默认 SQLite 均可；联调用默认 SQLite 即可）
cd /Users/hele/Projects/openlims/mp-pm/backend && PORT=8080 ./run.sh
# 3) mp-pm 前端
cd /Users/hele/Projects/openlims/mp-pm && npm run dev
```

- [ ] **Step 2: 确认真实 token 的角色 claim 形状（关键核对）**

登录后在浏览器 DevTools Console 跑：
```javascript
JSON.parse(atob((JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('oidc.user'))).access_token ?? '')||'')))
```
或更稳妥：复制 Local Storage 里 `oidc.user:*` 的 `access_token`，在 https://jwt.io 或 `python3 -c "import jwt,sys;print(jwt.get_unverified_claims(...))"` 解码，确认角色所在字段。
Expected: 能看到角色（预期在 `roles` 数组，元素含 `name`）。若实际字段与 `extract_role` 兼容分支不符，回到 Task 6 Step 5 增补对应分支并补一条单测，再继续。把确认结果记入 `docs/apps/mp-pm.md` 第 4 节。

- [ ] **Step 3: 正向 e2e —— cmc_lead 可见管理功能**

浏览器 `http://localhost:5175`，以 `guo.cmc / Maibo@2026` 登录。
Expected: 回到首页；顶栏/页面显示「郭主任」；`/auth/me` 返回 200（Network 面板可见）；能进入「模板」「项目新建」等 `cmc_lead` 有权的功能。

- [ ] **Step 4: 负向 RBAC —— rd 被拒**

退出登录（清 Local Storage 后刷新），以 `liu.usp1 / Maibo@2026`（角色 `rd`）登录。
Expected: 看不到/进不去 `project.create`、`template.edit`、`user.manage` 等仅高权角色可用的功能（前端 `can()` 按 `rd` 收敛）；若直接调后端受保护接口，返回 403。

- [ ] **Step 5: 负向 RBAC —— 后端接口级校验**

挑一个用 `require_role(...)` 保护的接口（如 `backend/app/api/v1/users.py` 中的管理类接口），用 `rd` 用户的 token 直接请求：
```bash
TOKEN="<liu.usp1 的 access_token>"
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/users
```
Expected: 返回 `403`（角色不足）。换 `admin` 用户 token 同接口返回 `200`。

- [ ] **Step 6: 写 `README.md`**

```markdown
# mb-casd —— 迈博药业 IAM 中台

基于 Casdoor 的 IAM 中台（官方镜像 / 品牌化 / Postgres / OIDC+PKCE / 仅中文）。

## 快速开始
1. `cp .env.example .env` 并填写口令与 `CASDOOR_TAG`
2. `docker compose up -d`
3. 管理台：http://localhost:8000 （内置 admin，首次请改口令）

## 接入上层应用
见 `docs/apps/<app>.md`（首个试点 `mp-pm`）。OIDC 端点：
- 授权：`/login/oauth/authorize`
- 令牌：`/api/login/oauth/access_token`
- JWKS：`/.well-known/jwks`

## 端口
- Casdoor 8000 / mp-pm 后端 8080 / mp-pm 前端 5175

## 设计与决策
- 设计 spec：`docs/superpowers/specs/2026-06-28-mb-casd-iam-design.md`
- CDN/内网取舍：`docs/decisions/0001-static-assets-cdn.md`
```

- [ ] **Step 7: 收尾文档 + 提交两仓**

更新 `docs/apps/mp-pm.md`：勾掉「接入改造清单」全部项，「变更记录」加一行（2026-06-28 端到端接入完成 + 确认角色 claim 字段）。
```bash
cd /Users/hele/Projects/openlims/mb-casd
git add README.md docs/apps/mp-pm.md
git commit -m "docs: e2e 联调通过 + README + 接入档案收尾（P4c）"
# mp-pm 仓如有 Task 6 Step 2 的兼容性补丁，单独提交
```

- [ ] **Step 8: 验收对照 spec §13**

逐条确认：① 一条 `docker compose up` 起全栈、管理台中文+迈博品牌；② Casdoor 内有 mp-pm 应用、6 角色、6 测试用户；③ mp-pm 真机端到端登录闭环，按角色可见/被拒；④ `docs/apps/mp-pm.md`、`docs/decisions/0001-static-assets-cdn.md`、`README.md` 齐备。全部满足即本期完成。

---

## 备注：偏离标准 TDD 的说明

Task 1–4 是基础设施/配置（docker-compose、Casdoor 初始化数据），无传统单元测试可写，故以**确定性的验证命令 + 预期输出**作为每个任务的验收门（等价于该任务的「测试」）。Task 6 是纯后端逻辑，按标准 TDD（先写失败测试 → 实现 → 通过）。Task 5/7 的前端与 e2e 以可复现的手动验证步骤兜底。
