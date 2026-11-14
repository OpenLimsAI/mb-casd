# ADR-0008：门户与项目管理的带凭据跨域登录

生产门户和项目管理通过浏览器直接调用 IAM，使用 `credentials: include`。
固定官方 v4.25.0 只为 IAM 自身来源返回带凭据的 CORS 许可；应用回调地址获准跨域不等于获准读取带 Cookie 的响应。
因此正常的会话检查和密码登录被浏览器判为网络失败，前端回退到 IAM 托管页。

保留固定官方源码和完整 v11 密码撤销／本人策略补丁，另叠加最小来源配置补丁。
新增 `credentialedOrigins`，默认空；只接受精确 HTTPS Origin，以逗号分隔。
生产配置为 `https://www.openlims.ai,https://pm.openlims.ai`，不信任其他子域名、不同端口、HTTP、路径或通配符。
原有同源行为不变，内部 TLS 代理和 OAuth redirect URI 不变。

同一判断同时用于 CORS 回复、Cookie 请求的权限过滤和绑定凭据的来源检查。
否则只加响应头会造成许可与身份校验不一致。获准网页可以使用 IAM Cookie，因此只允许由本组织控制的应用来源。
`Access-Control-Allow-Origin` 返回请求中的精确来源，`Access-Control-Allow-Credentials` 为 `true`，保留 `Vary: Origin`。
未获准来源保留原有拒绝／不带凭据跨域行为。

构建执行 HTTPS 来源护栏测试；合成 HTTP 回归覆盖两个来源的直接密码登录、会话 Cookie、PKCE/nonce、密码错误、Cookie 退出、预检及恶意来源。
默认空配置另行回归，并保留原有 v11 安全与兼容矩阵。合成回归不使用生产账号或数据库。

发布前备份现有配置、镜像及 IAM 数据库，按镜像 digest 切换 IAM 单个服务。
不改变数据库模型和账号权限；回滚恢复旧配置及旧镜像，不依赖构建标签。
