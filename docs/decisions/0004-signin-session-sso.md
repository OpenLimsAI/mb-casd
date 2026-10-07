# ADR-0004：开启 IAM 会话复用，实现跨应用单点登录

- 状态：已接受
- 日期：2026-10-07
- 相关：[`docs/apps/maibo-portal.md`](../apps/maibo-portal.md)、[`docs/apps/mp-pm.md`](../apps/mp-pm.md)、[`docs/apps/dikw.md`](../apps/dikw.md)、[`docs/apps/dikw-web.md`](../apps/dikw-web.md)

## 背景

组织 `mabpharm` 下有 4 个上层应用，都用 OIDC 授权码流程登录：

| Casdoor 应用 | 入口 |
|---|---|
| `maibo-portal` | 员工门户 `https://www.openlims.ai` |
| `mp-pm` | 项目管理 `https://pm.openlims.ai` |
| `dikw-kb` | 论文知识库 `https://kb.openlims.ai` |
| `dikw-web` | 知识库管理工作台（SSH 隧道 `http://localhost:4330`） |

2026-10-07 之前，用户在每个应用登录时都要输一次密码，在 IAM 控制台 `https://iam.openlims.ai` 也要再输一次。

原因在 Casdoor 3.100.0 的两个应用开关：

- `enableSigninSession`：授权码流程登录成功后，在 `iam.openlims.ai` 保留 IAM 会话（cookie）。不开时，Casdoor 只发授权码，不保留会话（源码 `controllers/auth.go:177-181`）。4 个应用原来都没开，所以下一个应用的登录页看不到已登录的账号。
- `enableAutoSignin`：已有同组织的 IAM 会话时，登录页自动完成登录（源码 `web/src/auth/LoginPage.js:136`）。不开时，登录页显示「继续使用 <账号>」，要点一下。

IAM 会话的有效期由 `cookieExpireInHours` 决定。0 表示 720 小时。用户登录时没有勾选「下次自动登录」，有效期最长 24 小时（源码 `controllers/auth.go:287-299`）。

## 决策

4 个应用都设置：

| 字段 | 值 |
|---|---|
| `enableSigninSession` | `true` |
| `enableAutoSignin` | `true` |
| `cookieExpireInHours` | `168`（7 天，与知识库会话的最长时间一致） |

- 2026-10-07 23:25 UTC 生效，经 Casdoor 管理接口 `get-application` / `update-application` 修改，没有重启服务。
- 改前改后对比数据库，每个应用只变了这 3 列。
- 改前快照在服务器 `~/mb-pm-v2/private-config-backups/20261007T232541Z-sso-session/`（含 client secret，权限 600）。回滚：把快照里的应用对象原样写回。

## 影响

- 在任一应用输一次密码。之后打开其他应用，直接进入，不用再输密码。
- 自动登录不给权限。每个应用仍按自己的规则检查角色：
  - PM 要求恰好一个 PM 角色，并且有同用户名的业务成员；
  - 论文知识库要求 `kb_viewer` 或 `kb_editor`；
  - 管理工作台要求 `dikw-admin`。
- IAM 会话：勾选「下次自动登录」保持 7 天（登录页默认勾选），不勾选保持 24 小时。
- 退出：
  - 在门户或 PM 点退出，会请求 Casdoor `/api/logout`，清掉 IAM 会话。
  - 其他应用自己的会话不受影响，要等到期：门户和 PM 最长 1 小时，论文知识库闲置 8 小时、最长 7 天。
- 换账号：先在门户或 PM 点退出。否则登录页会自动以当前账号登录。
- 共享电脑：7 天内，用这台浏览器的人都能直接打开有权限的应用。在共享电脑上登录时，不要勾选「下次自动登录」。

## 约束

- ⚠️ 不要关掉这 4 个应用的 `enableSigninSession`。关掉后，从这个应用登录不再留下 IAM 会话，用户又要在每个应用输密码。
- 新接入 `mabpharm` 的应用，同样打开这两个开关，`cookieExpireInHours` 设成 168。从现有应用克隆配置时，这些字段会一起带过去，核对一下即可。
- 修改应用时，先确认 `get-application` 返回的 `clientSecret`、`cert`、`tokenFormat` 不是 `***`。用应用的 client id / secret 调用时，Casdoor 把调用方当成全局管理员，返回的是完整对象。如果返回的是 `***` 并原样写回，`cert` 和 `tokenFormat` 会被覆盖，所有登录都会失败（`update-application` 只跳过 `clientSecret` 的 `***`）。

## 验证

2026-10-07 在 Chrome 里用 `mabpharm/hele.hl` 验证：

1. 打开论文知识库，输入一次密码（23:27:56 UTC）。
2. 打开门户，点「使用迈博账号登录」，直接进入工作台，没有密码框。
3. 打开 `https://iam.openlims.ai`，直接进入应用列表。
4. 打开 `https://pm.openlims.ai/api/v1/auth/login`，重新走一遍授权，直接进入 PM。

Casdoor 的 `token` 表里，`maibo-portal` 和 `mp-pm` 都签发了新 token，说明这两次是完整的授权流程，不是沿用应用自己的旧会话。管理工作台没有测，它需要 SSH 隧道。

## 不选的方案

| 方案 | 不选的原因 |
|---|---|
| 只开 `enableSigninSession` | 不用输密码，但每个应用都要点一次「继续使用」。用户要求完全不用操作 |
| 有效期保持默认的 30 天 | 用户选了 7 天，与知识库会话的最长时间一致 |
