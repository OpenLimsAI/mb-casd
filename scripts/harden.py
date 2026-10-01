#!/usr/bin/env python3
"""部署后加固：关闭 Casdoor 内置应用 app-built-in 的公开注册（见 ADR-0002）。

Casdoor 首次启动时由 InitDb() 创建 app-built-in，写死 EnableSignUp=true；
init_data 在 initDataNewOnly=true 下会跳过已存在的应用，无法覆盖该默认值，
所以只能在 Casdoor 起来后经管理 API 修改。脚本幂等，可在每次部署后重复执行。

凭据从环境变量读取（任一具备 Casdoor 管理权限的应用 client id / secret）：
    CASDOOR_ENDPOINT        例：http://127.0.0.1:8000（默认）
    CASDOOR_CLIENT_ID
    CASDOOR_CLIENT_SECRET

用法：
    python3 scripts/harden.py --check            # 只检查，未加固时退出码 1
    python3 scripts/harden.py --backup-dir DIR   # 修改前把应用原配置存到 DIR（含密钥，权限 600）
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUILTIN_APP = "admin/app-built-in"


def casdoor(method: str, path: str, *, params=None, body=None) -> dict:
    endpoint = os.environ.get("CASDOOR_ENDPOINT", "http://127.0.0.1:8000").rstrip("/")
    try:
        client = f"{os.environ['CASDOOR_CLIENT_ID']}:{os.environ['CASDOOR_CLIENT_SECRET']}"
    except KeyError as exc:
        sys.exit(f"缺少环境变量 {exc.args[0]}")
    url = f"{endpoint}/api/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {
        "Authorization": "Basic " + base64.b64encode(client.encode()).decode(),
        "Accept-Language": "zh",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=15) as response:
        result = json.loads(response.read())
    # Casdoor 业务失败时 HTTP 仍为 200，status=error。
    if result.get("status") != "ok":
        sys.exit(f"Casdoor {path} 失败：{result.get('msg')}")
    return result


def get_builtin_app() -> dict:
    app = casdoor("GET", "get-application", params={"id": BUILTIN_APP}).get("data")
    if not isinstance(app, dict) or app.get("name") != "app-built-in":
        sys.exit("未找到 app-built-in")
    # 非管理凭据拿到的是打码对象，写回会把 clientSecret 覆盖成 ***。
    masked = [k for k, v in app.items() if isinstance(v, str) and v and set(v) == {"*"}]
    if masked:
        sys.exit(f"返回的应用字段被打码（{masked}），凭据缺少管理权限，拒绝写回")
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="只检查，不修改")
    parser.add_argument("--backup-dir", type=Path, help="修改前备份应用原配置的目录")
    args = parser.parse_args()

    app = get_builtin_app()
    if app.get("enableSignUp") is False:
        print("app-built-in 公开注册已关闭，无需修改")
        return
    if args.check:
        print("app-built-in 公开注册仍开启（built-in 组织用户即全局管理员），需执行加固")
        sys.exit(1)

    if args.backup_dir:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = args.backup_dir / f"app-built-in.{stamp}.private.json"
        args.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup.write_text(json.dumps(app, ensure_ascii=False))
        backup.chmod(0o600)
        print(f"原配置已备份：{backup}")

    app["enableSignUp"] = False
    casdoor("POST", "update-application", params={"id": BUILTIN_APP}, body=app)
    if get_builtin_app().get("enableSignUp") is not False:
        sys.exit("写回后复核失败：app-built-in 公开注册仍开启")
    print("已关闭 app-built-in 公开注册")


if __name__ == "__main__":
    main()
