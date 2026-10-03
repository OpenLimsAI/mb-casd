# ADR-0003：上层应用的服务端 OIDC 调用走同名 TLS 代理（iam-proxy）

- 状态：已接受
- 日期：2026-10-03
- 相关：[`deploy/iam-proxy/`](../../deploy/iam-proxy/README.md)、[`docs/apps/dikw.md`](../apps/dikw.md)

## 背景

生产 IAM 部署在 maibo-prometheus 的 `mb-pm-v2` compose 栈里（`casdoor` + `iam-db`，与新 PM 共用 Docker 网络 `mb-pm-v2_internal`），公网地址 `https://iam.openlims.ai` 经该栈的 Cloudflare 隧道发布。上层应用（知识库、后续的 managed-agent console / platform）也跑在同一台机器上。

OIDC 授权码流程里，浏览器跳转不受影响，但以下调用由**应用服务端**发起：discovery、用授权码 / refresh token 换 token、拉 JWKS 验签（部分应用还会调 userinfo / introspection）。这台机器访问 Cloudflare 很不稳定：2026-10-03 实测，服务端访问公网 discovery 5 次只成功 1 次，成功的也要 10 秒以上。这些调用必须走内网。

各应用的能力不一样：

| 应用 | 能否指定 IdP 内网地址 | 限制 |
|---|---|---|
| dikw-web | 能（`DIKW_WEB_OIDC_INTERNAL_URL`） | 内网段为明文 http |
| managed-agent console 0.7.0 | 不能，只从公网 issuer 推导所有端点 | 端点必须 https（或回环 http） |
| managed-agent platform 0.4.0 | 能单独配置 `IDENTITY_OIDC_JWKS_URL` | 强制 https，且拒绝回环地址 |

## 决策

在部署机上运行**同名 TLS 代理** `iam-proxy`（配置见 `deploy/iam-proxy/`）：

1. Caddy 用自建 CA（`tls internal`）给 `iam.openlims.ai` 签证书，在专用的 `internal` 网络 `iam-oidc` 上以别名 `iam.openlims.ai` 提供 https，经 `mb-pm-v2_internal` 转发到 `casdoor:8000`。
2. 只放行服务端 OIDC 路径：discovery、JWKS、token、userinfo、introspection。其余一律 404。
3. 上层应用加入 `iam-oidc`，只读挂载 CA 根证书并信任它，issuer 照常配置为公网值。应用侧不需要任何「内网地址」配置项。

## 备选方案

- **每个应用各自加「内网地址」配置项**：要等每个应用实现并发版（console 目前没有）；内网段通常是明文 http；platform 本来就强制 https JWKS，仍然需要 TLS 代理。不采用。dikw-web 已有的配置项保留不用。
- **把别名放在共享网络 `mb-pm-v2_internal` 上**（省一张网）：Docker 网络别名对同网所有容器生效，新 PM 等容器对 `iam.openlims.ai` 的访问会被劫持到自签证书上，它们不信任这个 CA，登录会直接失败。否决。
- **修好部署机到 Cloudflare 的出网**（出网代理 / 换线路）：能从根上解决，但不在本仓库可控范围内，成本也高。如果以后解决了，可以撤掉代理，应用改回直连公网。

## 后果

好处：

- 不改应用代码，现有版本（dikw-web 0.11.0、console 0.7.0、platform 0.4.0）都能用。
- 内网段是校验证书的 https，比明文的内网地址方案更安全。
- 所有应用共用一个代理；对外只暴露 5 个服务端 OIDC 路径。

代价：

- 同名解析有理解成本：容器里的 `iam.openlims.ai` 不是公网那个，排查时要知道这一点（README 已写明）。
- 多一个组件和一个 CA 要维护：`caddy-data` 卷丢失会生成新 CA，要重新分发根证书并重启各使用方。
- Go 应用的 `SSL_CERT_FILE` 会替换系统根证书，需要准备「系统根证书 + 本 CA」的合并文件。
- 依赖 `mb-pm-v2_internal`：mb-pm-v2 重建网络后，代理要重新接上。

## 验证（dikw-web，2026-10-03）

- dikw-web 只接 `dikw_dikw_net` 和 `iam-oidc`，容器里 `iam.openlims.ai` 解析到代理，`casdoor` 无法解析。
- 登录跳转经代理拿 discovery（200）。会话续期时 token 端点 200、JWKS 200，Casdoor 签发了新 token。
- 非白名单路径（登录页、动态注册、`/api/get-account`）返回 404；不信任 CA 的容器 TLS 被拒（`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`）。
