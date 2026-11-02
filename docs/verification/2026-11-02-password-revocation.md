# 密码撤销：独立 PostgreSQL / IAM 合成数据验证

状态：修正版候选行为验收通过；不是生产发布记录。最终仍须在合并后的固定 Go 1.25.8 Docker 构建镜像上重复运行。

## 隔离条件

- 原始源码 `7325999791deaeab538f86082d70858d0ab4d773`，精确补丁应用后编译 Linux/amd64。
- 本次先验候选使用缓存 Go 1.26.0；仅将 `/server` 只读挂入原生产同版本官方基础镜像，其他 UI/资源不变。
- 候选二进制 SHA-256：`b911225d59fdd50d4dfcfbf65a0ff905a8b17cf988065d9ead828eab3d61e759`。
- 专用 `maibo-iam-security-20261102` internal 网络。IAM 容器同名，空测试 PostgreSQL 为 `maibo-iam-security-db-20261102`，均带 `purpose=maibo-iam-security-validation` 标签。
- 两容器没有发布任何端口、没有加入生产网络、没有挂载生产数据。数据库使用本次 tmpfs，组织、应用、用户全部合成。
- 随机测试凭据、会话及令牌仅在服务器私有目录和测试进程内使用；未复制到开发电脑。测试管理员的初始默认口令在开始验证前已替换。

## 发现与修复

第一版在真实 PostgreSQL 上发生“改密返回成功但 token 未撤销”。原 `ExpireTokenByUser` 的条件 `user = ?` 在 PostgreSQL 中引用了数据库当前用户表达式，而不是 token 表的用户列。隔离库中 alice 有两条 token；未引用条件匹配 0 条，引用 `"user"` 后匹配 2 条，数据库不报 SQL 错误。

修正版将撤销、活跃令牌枚举及通知枚举统一改为 XORM 方言引用固定列名，值继续使用绑定参数。新增 PostgreSQL/MySQL 方言单测；固定原始 archive 上 `git apply --check` 成功，原有撤销失败路径回归和新方言回归均通过。

## 实际 HTTP 结果

使用 `scripts/verify_password_revocation.py`，每一轮都建立同一用户在两个不同应用中的独立真实 SSO 会话和授权码 + PKCE 令牌，并先刷新一次其中的令牌链。

| 入口 | 旧 access 失效 | 原/轮转 refresh 拒绝 | 两个旧 SSO 无法快速登录 | 其他用户及管理员保留 | 新密码可登录 |
|---|---|---|---|---|---|
| 本人 `set-password` | 通过 | 通过 | 通过 | 通过 | 通过 |
| 管理员 `set-password` | 通过 | 通过 | 通过 | 通过 | 通过 |
| 管理员 `update-user?columns=password` | 通过 | 通过 | 通过 | 通过 | 通过 |

`columns=password` 按上游既有存储格式契约传 bcrypt 哈希；它不是接收明文的原生改密入口。本补丁不改变导入语义。测试脚本使用客户服务器 Python 3.12 的 `crypt`；Python 3.13 以后须先替换这一测试专用哈希工具。

另验证 `needUpdatePassword=true` 时原生登录响应包含需改密标志；通过本人原生改密后标志清除。本结果不替代 PM/知识库业务端强制改密 gate 的独立回归。

## 后续复验与清理

服务器私有目录：`~/security-iam-validation-20261102`。`private.json`、配置、运行记录均为 0600，目录为 0700；`results.json` 只有上述布尔结果。验证脚本会检查专用容器标签、内部网络、无发布端口、endpoint 与容器 IP 一致，再访问合成账号。

最终镜像构建好后，仅替换此测试 IAM 容器为该固定镜像，保留空测试 PG 实例及合成数据，更新私有 endpoint，再执行同一脚本。不要把此脚本指向生产 IAM。

验证完成后的清理清单：删除这两个专用测试容器，删除同名测试网络，最后删除本次私有测试目录及候选二进制。`cleanup.txt` 已保留容器/网络精确名称；只清理本次创建的对象，不执行全局 prune，不删除任何生产卷。当前保留隔离环境供最终固定镜像复验。
