# 固定 v4 安全协议回归

从仓库根目录执行，先安装 Docker 和 Python 3.11+；Python 只使用标准库驱动生命周期，不在宿主安装 pytest。Docker 工具镜像使用已验证的哈希锁定依赖子集。

```sh
python tests/test_release_packaging.py
python -m unittest discover -s tests/iam_v4 -p 'test_*.py'
python tests/v4-revocation/fetch_source.py
docker build -f build/Dockerfile.v4-password-revocation -t mb-casd-v4:local .
docker build -f tests/iam_v4/Dockerfile.tools -t mb-casd-iam-v4-tools:local .
python tests/iam_v4/run_security.py --run-tag local1 --replica
python tests/iam_v4/run_compatibility.py --mode policy --run-tag local2
python tests/iam_v4/run_compatibility.py --mode default-off --run-tag local3
```

run-tag 必须新唯一、1–8个小写字母／数字／短横线；已有输出不覆盖。驱动只解析已有的 local/ci 标签或 canonical ID，核验固定官方源码标签、v11 补丁标签及 `/server` SHA256，再绑定实际 image ID；不自动拉取、不仅凭标签信任内容。这样允许冷构建元数据不同但二进制完全一致的镜像，未知二进制仍拒绝。只创建新空 PG18 tmpfs、内部网络和临时工具／IdP 容器，没有宿主端口。两合成用户、五个 DCR 客户端、精确三个本人退出客户端和两个策略客户端固定；refresh grant 只用于合成 PM 的安全矩阵，令牌最长一小时。创建这些临时访问前须取得环境需要的许可，不涉及既有身份实例。

所有凭据只在内存或新容器 tmpfs，输出 `.runs/` 已忽略。finally 按记录的 ID／标签清理；创建结果不明时保留 pending 并停止，先核实，不盲目重试或删除同名资源。只保留状态、非秘密断言和源码／镜像指纹；不要整目录提交或上传原始运行记录。

18项套件涵盖改密撤销、存储读取／更新故障、授权码与 refresh 并发、事务失败恢复和其他用户隔离。16项兼容矩阵涵盖本人固定投影及设备／全设备退出；3项默认关闭矩阵保留旧行为。它们是实际 HTTP／数据库实验，不是浏览器密码登录或签名截图验收。`password_v8_regression.py` 等内部文件名保留断言来源，不表示运行旧镜像。

CI 的 v4-backport 作业在同一次完整构建后运行同一协议入口，避免重复冷编译；main 既有 v3 作业保留。外部目录、MFA、找回密码正向、MySQL、离线JWT、所有真实多设备与生产迁移不在该矩阵内。测试不修改 maibo、正式账号或正式配置。
