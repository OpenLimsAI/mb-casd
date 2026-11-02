# ADR-0006：密码变更撤销所有授权的最小安全补丁

日期：2026-11-02；状态：代码候选，须构建、CI 和隔离验收后部署。

## 原因与范围

审计确认生产 Casdoor 3.152.0 的 `set-password` 会保存新密码并写改密时间，但不会撤销已发放的 access/refresh token 或 SSO 会话。只有上层应用比较 JWT `iat` 不能解决旧 refresh token 换取新 `iat` 的问题。

用户已明确授权系统性修复审计问题并部署。本项作为“仅配置、不改 Casdoor 源码”原则的受限安全例外：保持官方固定版本 UI、资源和运行镜像，仅对生产同版本源码的两个密码写入入口加撤销操作，不维护长期功能分叉。上游后续完整覆盖这些行为后删除补丁，回归官方镜像。

上游对照：Casdoor master 固定提交 `c3f9ddd8cb9ae184b0f73a6c879d01688efab3c7` 已在密码修改后调用 `ExpireTokenByUser`，但仍未在该路径销毁 SSO 会话。本补丁使用 3.152.0 已有的全局退出原语，补齐 SSO 端。

## 固定供应链

- 源码：`casdoor/casdoor@7325999791deaeab538f86082d70858d0ab4d773`，tag `v3.152.0`。
- GitHub API tarball SHA-256：`8ce76d5508bbb1b5ac0cb0bf366089732a75269ea69c53a1de3862957696a18d`。
- 生产基底：`casbin/casdoor@sha256:95c7be68fb98daf2ec74a10c9f785af1ef75e8fef6dd4aad455a899e651e87e2`。
- 构建：`build/Dockerfile.password-revocation`；精确 patch、`--fuzz=0`，任何源文件漂移直接构建失败。
- 候选只覆盖 `/server`，不包含客户数据、凭据或 init_data；构建上下文白名单仅包含补丁和构建定义。

## 行为

1. `SetPassword` 成功保存密码后，向当前用户的各应用发送既有 backchannel 通知，再将该用户全部 token 记录置为失效、销毁所有真实 Beego SSO 会话。
2. `UpdateUser` 显式写入 password/password_salt/password_type 且值发生变化时，写入真实改密时间并执行同样撤销；普通资料、角色编辑不会退出其他会话。
3. 改密者正是当前会话主体时，同步清除当前会话身份与令牌，避免响应结束时把已销毁的登录写回会话存储；管理员为他人重置不退出管理员。
4. token 和 SSO 两项清理都会尝试；任一失败向调用方明确返回“密码已改变，但撤销未完成”，不得误报成功。通知是辅助机制，撤销不依赖其他应用是否在线收到通知。
5. 3.152.0 `RefreshToken` 已检查 `ExpiresIn <= 0`，旧刷新链不能凭已失效的 token 记录继续换票。

## 验收与回滚

在独立测试数据库、网络和专用账号中验证，不使用客户现有账号：

- 在 PM、门户、知识库和 IAM 建立多个独立会话；至少让一个应用完成一次 refresh。
- 分别覆盖 IAM 原生本人改密、管理员 `set-password` 重置、`update-user?columns=password`（仅隔离环境）。
- 旧 access introspect 必须 `active=false`，旧 refresh 必须 `invalid_grant`，旧 IAM cookie 不能静默签入新应用；其他用户的 token/SSO 不受影响。
- 新密码可以重新登录；临时密码标记在 IAM 上为 true 时，任何业务应用均要求先改密；完成后 clear。
- 模拟 token/session 存储失败，确认不会返回成功。撤销成功但客户端离线时，下一次请求仍被 PM/KB 的实时 gate 拒绝。

候选回滚只换回上面的官方镜像 digest，无新增 IAM 数据库表。回滚会重新暴露原生改密不撤销授权的限制，须记录并暂停相关操作，不能把回滚视为安全修复完成。

构建命令：

```sh
docker build --platform linux/amd64 -f build/Dockerfile.password-revocation -t maibo-iam-password-revocation:7325999-v1 .
```
