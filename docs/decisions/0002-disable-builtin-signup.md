# ADR-0002：部署后关闭内置应用 app-built-in 的公开注册

- 状态：已接受
- 日期：2026-10-01
- 相关：D1（官方镜像 / 不改源码）

## 背景

2026-10-01 核查生产 IAM（`iam.openlims.ai`）时发现，Casdoor 内置应用 `app-built-in` 的 `enableSignUp=true`，经公网 `GET /api/get-application?id=admin/app-built-in` 可直接确认。

对照 Casdoor `v3.100.0` 源码：

- `object/user.go`：`IsGlobalAdmin()` 返回 `user.Owner == "built-in"` —— **built-in 组织的任何用户都是全局管理员**，可管理所有组织、应用、证书与密钥。
- `object/init.go`：`initBuiltInApplication` 创建 `app-built-in` 时写死 `EnableSignUp: true`（上游默认值，非误配）。
- `main.go`：先 `InitDb()`（建 built-in 组织 / 应用），后 `InitFromFile()`；`object/init_data.go` 中已存在的应用在 `initDataNewOnly=true` 下直接跳过。

即：任何人若能在 `app-built-in` 完成注册，就能拿到整个 IAM 的管理权。当前注册表单要求邮箱验证码，未配置发信 Provider 时实际难以完成，但这只是偶然的阻断，不能当作防线。

## 决策

**每次部署（含全新部署与升级）后执行 `scripts/harden.py`，经管理 API 把 `app-built-in` 的 `enableSignUp` 改为 `false`。**

不采用的方案：

- **在 `init_data.json` 里声明 `app-built-in`**：无效。`InitDb()` 总先建出它，随后 `initDataNewOnly` 跳过同名项，全新部署也一样。
- **改 `initDataNewOnly=false`**：每次启动用 init_data 覆盖已有数据，须完整声明 `app-built-in` 全部字段，且会冲掉控制台里的运行期修改，风险更大。
- **改 Casdoor 源码 / 自建镜像**：违背 D1。

## 影响

- ✅ 关闭全局管理员的自助注册入口；不影响 `mp-pm` 等上层应用（各自应用的注册开关独立）。
- ✅ 脚本幂等，`--check` 可接入部署后验证。
- ⚠️ 这是部署流程的一步，不是声明式配置：新环境漏跑就会回到默认开启状态。部署后务必执行 `python3 scripts/harden.py --check`。
