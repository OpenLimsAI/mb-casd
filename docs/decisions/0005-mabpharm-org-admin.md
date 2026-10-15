# ADR-0005：把 guo.admin 设为 mabpharm 组织管理员

- 状态：已接受
- 日期：2026-10-15
- 相关：[ADR-0002](0002-disable-builtin-signup.md)、[`docs/apps/mp-pm.md`](../apps/mp-pm.md)、[`docs/apps/dikw.md`](../apps/dikw.md)、[`docs/apps/dikw-web.md`](../apps/dikw-web.md)、[`docs/apps/maibo-portal.md`](../apps/maibo-portal.md)

## 背景

2026-10-15 之前，只有 `built-in/admin` 能在 IAM 里添加用户。`mabpharm/guo.admin` 有 PM 的 `admin` 角色，但 PM 角色不是 Casdoor 的管理员。用户要求 guo.admin 自己能在 IAM 里添加用户。

Casdoor 3.100.0 按下面的顺序判断一个 API 请求能不能执行（`authz/authz.go:173-196`）：

| 调用方 | 结果 |
|---|---|
| 应用凭据（client id / secret） | 直接放行（第 173 行） |
| `built-in` 组织的用户（全局管理员） | 直接放行（第 187 行） |
| `is_admin=true` 的用户，对象在同一组织（组织管理员） | 直接放行（第 191 行） |
| 其他用户 | 按默认策略判断。默认策略里没有 `/api/add-user` |

改动前，生产上其他加人途径都是关的：

- 5 个应用的 `enableSignUp` 都是 `false`（ADR-0002 关了 `app-built-in`，其余 4 个本来就没开）。
- PM 后端只用应用凭据做两件事：本人改用户名、本人改密码。它不建 IAM 账号。
- `mabpharm` 下没有 `is_admin=true` 的用户。

## 决策

打开 `mabpharm/guo.admin` 的 `is_admin`。管理台里这个字段叫「是管理员」。

- 2026-10-15 14:02:13 UTC 生效，没有重启服务。
- 用应用凭据调 `update-user?id=mabpharm/guo.admin&columns=isAdmin`，请求体是 `{"isAdmin": true}`。带 `columns` 时，Casdoor 把请求体合并到数据库里的原用户上，其他字段不变。
- 改前改后对比数据库行，只变了 `is_admin` 和 `updated_time` 两列。
- 改前快照在服务器 `~/mb-pm-v2/private-config-backups/20261015T140212Z-guo-admin-org-admin/`（含密码哈希，权限 600）。
- 回滚：调同一个接口，请求体是 `{"isAdmin": false}`。

## 影响

guo.admin 能管理 `mabpharm` 下的这些对象。下表根据 3.100.0 源码整理。用户已在管理台确认能看到「用户」菜单，其他各项没有在管理台逐项实测。

| 对象 | 能做什么 | 依据 |
|---|---|---|
| 用户 | 添加、修改、删除、重置密码、禁用 | `authz/authz.go:191` |
| 角色 | 修改成员，包括 PM 的 `admin`、`kb_editor`、`dikw-admin`。也就是说，他能给任何人开通这 4 个应用 | `authz/authz.go:191` |
| 应用 `dikw-kb`、`dikw-web`、`maibo-portal`、`mp-pm` | 修改配置、删除、新建；读应用时拿到完整对象，包括 `clientSecret` | 应用的归属取自请求体里的 `organization`（`routers/authz_filter.go:34`、`:219`）；读应用时不遮掩（`object/application_util.go:243`，`object/user.go:1464` `IsApplicationAdmin`） |

⚠️ 警告：要按全局管理员保护 guo.admin 账号。原因：

1. guo.admin 能读到这 4 个应用的 `clientSecret`。
2. 用任一应用的 client id / secret 调 Casdoor API，Casdoor 直接放行（`authz/authz.go:173`）。
3. 所以拿到这个账号，实际上就能管理整个 IAM，包括 `built-in` 组织。

不受影响的部分：

- 全局管理员仍然只有 `built-in/admin`。
- PM、dikw-web、dikw-mbweb 的代码都不读 `isAdmin`（2026-10-15 在生产容器里搜过）。guo.admin 在这 3 个应用里的权限不变。`maibo-portal` 没有查。

## 添加用户的步骤

1. 用 guo.admin 登录 `https://iam.openlims.ai`。
2. 打开「用户」，点「添加」。
3. 在编辑页改用户名、显示名和密码，然后保存。
   - 「添加」会马上建出一个默认账号：用户名 `user_xxxxxx`，显示名 `New User - xxxxxx`，密码 `123`（`web/src/UserListPage.js:71`）。
   - ⚠️ 警告：不要保留默认账号。改好再保存；不用的账号要删掉。
4. 打开「需要修改密码」。用户下次登录任一应用时，Casdoor 先把他带到「我的账户」页改密码（`controllers/auth.go:194`、`web/src/auth/LoginPage.js:364`）。改完后，这个标志自动关闭（`controllers/user.go:659`）。这一步只核对过源码，没有在浏览器里实测。
5. 打开「角色」，把 `mabpharm/<用户名>` 加进需要的角色。
6. 如果要开通 PM，还要在 PM 的「组织」里建同用户名的成员（见 [`docs/apps/mp-pm.md`](../apps/mp-pm.md)）。

## 约束

- 只把组织管理员给能被信任管理整个 IAM 的人。原因见「影响」里的警告。
- 建议 guo.admin 开启 MFA。`mabpharm` 的账号设置允许用户本人开启 MFA。
- 不要把用户放进 `built-in` 组织来给管理权限。`built-in` 的任何用户都是全局管理员（ADR-0002）。

## 不选的方案

| 方案 | 不选的原因 |
|---|---|
| 继续只由 `built-in/admin` 添加用户 | 用户要求 guo.admin 自己能添加用户 |
| 把 guo.admin 放进 `built-in` 组织 | 那是全局管理员，范围更大 |
| 在 PM 里做「添加用户」功能，后端用应用凭据代建 IAM 账号 | 要开发 PM，用户要的是马上能在 IAM 里操作 |
