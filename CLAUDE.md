# CLAUDE.md — mb-casd

迈博药业（mabpharm）IAM 中台，基于 Casdoor。本目录是**定制化工作目录**：所有定制收敛在配置、静态资源、数据初始化里，**不 fork Casdoor 源码**。

## 当前状态

设计阶段已完成，**实施未开始**。权威设计见 `docs/superpowers/specs/2026-06-28-mb-casd-iam-design.md`。下一步：按该 spec 拆实施计划，落地 P1–P4。

## 关键决策（详见 spec §2）

- 仅品牌化，用官方预构建镜像 `casbin/casdoor`，**不改源码**（升级=换 tag）。
- 本机 / POC 优先；生产加固（TLS/反代/密钥/备份）留后续。
- 上层应用用 **OIDC 授权码 + PKCE** 登录，重定向到 Casdoor 托管登录页。
- **仅中文**（`forceLanguage=zh`）。
- 数据库：Postgres docker 实例。
- 本期端到端：含首个试点应用 **mp-pm** 的客户端接入改造（跨 mb-casd + mp-pm 两仓）。
- RBAC 职责：**Casdoor 管身份+角色分配；上层应用保留自身代码内的「角色→权限」矩阵**。

## 目录约定

```
docker-compose.yml   casdoor + postgres
conf/app.conf        挂载到容器 /conf/app.conf
init_data/           init_data.json（组织/应用/证书/RBAC/管理员种子）
assets/              迈博 logo / favicon / 登录页 CSS
deploy/iam-proxy/    部署机上的同名 TLS 代理（应用服务端 OIDC 调用走内网，ADR-0003）
docs/apps/<app>.md   每个接入应用一份档案（OIDC 配置 + 角色 + 权限矩阵 + 变更记录）
docs/decisions/      ADR（架构/取舍决策记录）
docs/superpowers/specs/   设计 spec
```

## 约定与红线

- **密钥只进 `.env`（已 gitignore），仓库放 `.env.example`。** 切勿提交真实凭证。
- **镜像钉死具体版本号**，不用 `latest`（可复现 + 可控升级）。
- 文档用中文。
- **每接入一个新上层应用**：在 `docs/apps/` 加一份档案；RBAC/权限变更记录在该档案的「变更记录」表里（单一变更跟踪源）。
- 改了上层应用的「角色→权限」矩阵，要同步更新对应 `docs/apps/<app>.md`。

## 外部位置

- 本地 Casdoor 源码（参考 / 后续源码构建用）：`/Users/hele/Projects/casdoor`（`v3.100.0`）。
- 首个试点应用 mp-pm：`/Users/hele/Projects/openlims/mp-pm`（前端 Vite+React+TS @5175；后端 FastAPI+SQLAlchemy+Postgres，已用 `python-jose`）。当前无真实登录（硬编码 CTO 用户），6 角色定义在 `src/lib/permissions.ts`。

## 运行（实施落地后）

`docker compose up` 一条命令起全栈；Casdoor 管理台 `http://localhost:8000`。详见 README（实施时补全）。
