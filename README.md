# mb-casd —— 迈博药业 IAM 中台

基于 Casdoor 的 IAM 中台（官方镜像 / 品牌化 / Postgres / OIDC+PKCE / 仅中文）。

## 快速开始

1. `cp .env.example .env` 并填写口令与 `CASDOOR_TAG`
2. `docker compose up -d`
3. 管理台：http://localhost:8000 （内置 admin，首次请改口令）
4. **加固（每次部署后必做）**：关闭内置应用 `app-built-in` 的公开注册（built-in 组织用户即全局管理员，见 ADR-0002）

   ```bash
   export CASDOOR_ENDPOINT=http://127.0.0.1:8000 CASDOOR_CLIENT_ID=... CASDOOR_CLIENT_SECRET=...
   python3 scripts/harden.py --backup-dir ./backups
   python3 scripts/harden.py --check   # 已加固时退出码 0
   ```

## 接入上层应用

见 `docs/apps/<app>.md`：`mp-pm`（CMC 项目管理系统，首个试点）、`dikw.md`（迈博知识库 `dikw-kb`，拆分后给论文知识库）、`dikw-web.md`（知识库管理工作台 `dikw-web`）。OIDC 端点：

- 授权：`/login/oauth/authorize`
- 令牌：`/api/login/oauth/access_token`
- JWKS：`/.well-known/jwks`

## 端口

- Casdoor 8000 / mp-pm 后端 8080 / mp-pm 前端 5175

## 设计与决策

- 设计 spec：`docs/superpowers/specs/2026-06-28-mb-casd-iam-design.md`
- CDN/内网取舍：`docs/decisions/0001-static-assets-cdn.md`
- 关闭内置应用公开注册：`docs/decisions/0002-disable-builtin-signup.md`
- 服务端 OIDC 调用走同名 TLS 代理：`docs/decisions/0003-server-side-oidc-via-iam-proxy.md`

## 部署机上的 iam-proxy

部署机访问不了公网 `iam.openlims.ai`，上层应用的服务端 OIDC 调用（discovery / token / JWKS）经同名 TLS 代理走内网。部署和接入方法见 [`deploy/iam-proxy/README.md`](deploy/iam-proxy/README.md)。
