# ADR-0001：本期用官方镜像，接受少量前端资源走 CDN

- 状态：已接受
- 日期：2026-06-28
- 相关：D1（仅品牌化 / 官方镜像）、D2（POC 优先）

## 背景

迈博 IAM 中台基于 Casdoor。UI 定制选择「仅品牌化、用官方预构建镜像 `casbin/casdoor`、不改源码」（D1），以换取最低维护成本和最简升级（换 tag 即可）。

官方预构建镜像的前端 build 中，部分静态资源默认从公共 CDN `cdn.casbin.org` 加载。这与官方「内网部署 / 静态资源本地化（deploy-intranet）」文档关注的问题相关。

## 决策

**本期（POC）接受少量前端资源走 `cdn.casbin.org`。**

- 品牌可定制部分（logo、favicon、产品名、主题色、登录页、强制中文）通过组织/应用配置 + 挂载本地 `assets/` + `staticBaseUrl` 实现，**不依赖 CDN**。
- 仅 Casdoor 前端 build 内置引用的少量资源仍可能走 CDN。POC 环境联网，无功能影响。

## 影响

- ✅ 维护成本最低，升级最简单（钉死 release tag，换 tag 即升级）。
- ✅ 迈博品牌可见部分完全本地化。
- ⚠️ 需联网才能加载那部分 CDN 资源；**完全内网 / 离线 / air-gap 场景本期不满足**。

## 后续（触发条件与升级路径）

当出现「完全内网 / 离线 / 不允许任何外部 CDN」硬性要求时，切换到**源码构建路线**：

1. 基于本地 casdoor 源码（`/Users/hele/Projects/casdoor`）构建自带迈博品牌 + 本地静态资源的镜像；
2. 按官方 deploy-intranet 文档将 `staticBaseUrl` 与前端资源完全本地化；
3. 产出自包含的 `mabpharm/casdoor` 镜像，无任何外部 CDN 依赖。

该路线工作量更大、升级时需对新 release 做 rebase，故仅在确有内网硬性要求时启用。
