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
