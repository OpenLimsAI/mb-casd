# iam-proxy：服务端 OIDC 调用的同名 TLS 代理

让部署机（maibo-prometheus）上的上层应用在**服务端**稳定访问 IAM。设计取舍见 [ADR-0003](../../docs/decisions/0003-server-side-oidc-via-iam-proxy.md)。

## 解决什么问题

IAM 的公网地址 `https://iam.openlims.ai` 经 Cloudflare 隧道发布，Casdoor 本身就跑在部署机上。浏览器登录不受影响，但 OIDC 有三类调用由应用服务端发起：discovery、用授权码 / refresh token 换 token、拉 JWKS 验签。部署机访问 Cloudflare 很不稳定（2026-10-03 实测公网 discovery 5 次成功 1 次，单次 10 秒以上），这些调用不能走公网。

## 工作方式

```
应用容器（加入 iam-oidc 网络）
  │  解析 iam.openlims.ai → iam-proxy（网络别名，只在 iam-oidc 上生效）
  │  https，证书由 iam-proxy 的自建 CA 签发，应用信任其根证书
  ▼
iam-proxy（Caddy）── 只放行 5 个服务端 OIDC 路径，其余 404
  │  经主机级共享网络 edge
  ▼
casdoor:8000
```

- 应用配置照常写公网 issuer（`https://iam.openlims.ai`），**不需要任何「内网地址」配置项**。Casdoor 返回的 discovery 里各端点都是 `https://iam.openlims.ai/...`，在应用容器里自然落到代理上。
- 放行的路径：`/.well-known/openid-configuration`、`/.well-known/jwks`、`/api/login/oauth/access_token`、`/api/userinfo`、`/api/login/oauth/introspect`。登录页、登出、动态注册（`/api/oauth/register`）、设备授权和管理 API 都不经这个名字暴露。
- `iam-oidc` 是 `internal` 网络，没有出网网关；成员各自的出网仍走自己的其他网络。

## 部署

```bash
# 在部署机上（目录与本仓库 deploy/iam-proxy/ 一致）
mkdir -p ~/iam-proxy/ca && cd ~/iam-proxy
# 放入本目录的 docker-compose.yml 与 Caddyfile
docker compose up -d
docker inspect -f '{{.State.Health.Status}}' iam-proxy          # healthy
# 导出 CA 根证书（公开证书，给应用挂载；首次启动签发证书后才出现）
docker exec iam-proxy cat /data/caddy/pki/authorities/local/root.crt > ca/root.crt
chmod 644 ca/root.crt
```

依赖主机级共享网络 `edge`（首次部署前 `docker network create edge`，不归任何栈所有；mb-pm 的 `compose.production.yml` 让 `casdoor` 加入它）。`ca/` 是每台机器各自的 CA，不入库（已 gitignore）。

## 接入一个应用

在应用的 compose 里：

```yaml
services:
  app:
    environment:
      # Node：在系统根证书基础上追加
      NODE_EXTRA_CA_CERTS: /etc/iam-proxy-ca.crt
    volumes:
      - /home/prometheus/iam-proxy/ca/root.crt:/etc/iam-proxy-ca.crt:ro
    networks:
      - default        # 应用自己的网络（出网、后端等）
      - iam_oidc

networks:
  iam_oidc:
    external: true
    name: iam-oidc
```

- **Node**（如 dikw-web、managed-agent console）：`NODE_EXTRA_CA_CERTS` 是追加，不影响访问其他网站。
- **Go**（如 managed-agent platform）：`SSL_CERT_FILE` 会**替换**默认根证书列表。只放本 CA 会让该进程访问其他 https 站点（外部 MCP、vault 校验等）全部失败，要准备「系统根证书 + 本 CA」的合并文件，例如 `cat /etc/ssl/certs/ca-certificates.crt ca/root.crt > ca/bundle.crt`。
- 只挂 `root.crt`，**不要**挂 `caddy-data` 卷（里面有 CA 私钥）。
- 应用不要为了连 Casdoor 加入 `mb-pm-v2_internal` 或 `edge`：只接 `iam-oidc`，容器里解析不到 `casdoor`，能证明只走代理。

接入后验证：应用日志无鉴权配置错误；`docker logs iam-proxy`（JSON 访问日志）里能看到该应用 IP 对 discovery / token / JWKS 的 200；完整走一次登录或会话续期。

## 红线

- **别名只放在 `iam-oidc` 上。** Docker 网络别名对同网络所有容器生效；放到 `edge`、`mb-pm-v2_internal` 这类共享网络，会把 mp-pm 等对 `iam.openlims.ai` 的访问劫持到自签证书上，它们不信任这个 CA，登录直接失败。
- 白名单只增不随手开：新应用需要别的服务端端点时，先说明用途再改 Caddyfile。

## 运维

| 场景 | 处理 |
|---|---|
| mb-pm-v2 被 `compose down` / `up` | 无需处理：`edge` 是主机级网络，不随 PM 栈重建；casdoor 重建后按服务名重新解析 |
| `edge` 网络被误删 | `docker network create edge`，再依次 `up -d` 各个接入它的栈（mb-pm-v2、dikw 的 caddy、iam-proxy） |
| `caddy-data` 卷丢失 | 启动后会生成**新 CA**：重新导出 `ca/root.crt`，并重启所有使用方 |
| 证书轮换 | 根证书有效期 10 年；中间证书和叶子证书由 Caddy 自动轮换，使用方只信任根证书，无需操作 |
| 排查 | `docker logs iam-proxy`；注意容器里的 `iam.openlims.ai` 不是公网那个 |

## 当前使用方

| 应用 | 接入日期 | 说明 |
|---|---|---|
| dikw-web（`kb.openlims.ai`） | 2026-10-03 | 取代 `DIKW_WEB_OIDC_INTERNAL_URL`；discovery、续期换 token、JWKS 验签均已验证，见 [docs/apps/dikw.md](../../docs/apps/dikw.md) |
