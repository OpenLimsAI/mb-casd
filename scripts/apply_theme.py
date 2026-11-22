#!/usr/bin/env python3
"""幂等同步 MBERP Swiss Clinical v2 登录主题至 Casdoor 组织与应用（仅修改主题与登录 CSS 字段）。

由于 init_data.json 在 initDataNewOnly=true 下不会覆盖既有数据库记录，
本脚本提供与 scripts/harden.py 一致的受控管理 API 同步能力：
  - 仅允许更新组织的 themeData，以及应用的 themeData / formCss / formCssMobile；
  - 写入前先读取全部目标记录，核验非打码密钥与归属组织（mabpharm），并写入 0700/0600 私密备份；
  - 每次写入后回读校验：除主题字段外的所有认证、OIDC、CORS、会话与角色配置必须逐字段完全一致，否则自动回滚。

环境变量（与 scripts/harden.py 一致）：
    CASDOOR_ENDPOINT        例：http://127.0.0.1:8000（默认）
    CASDOOR_CLIENT_ID
    CASDOOR_CLIENT_SECRET

用法：
    python3 scripts/apply_theme.py --check
    python3 scripts/apply_theme.py --backup-dir ./backups
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
CSS_SOURCE_PATH = ASSETS_DIR / "swiss-clinical-login.css"
ORG_PATCH_PATH = ASSETS_DIR / "organization-theme.patch.json"
APP_PATCH_PATH = ASSETS_DIR / "application-theme.patch.json"

ORG_ID = "admin/mabpharm"
ORG_NAME = "mabpharm"
DEFAULT_APPS = ("maibo-portal", "mp-pm", "dikw-kb", "dikw-web", "maibo-mdm")
APP_THEME_FIELDS = frozenset({"themeData", "formCss", "formCssMobile"})


def _non_theme_app_projection(record: dict) -> dict:
    """Project all non-theme fields of an application, normalizing Casdoor's embedded organizationObj.themeData mirror."""
    projected = {k: v for k, v in record.items() if k not in APP_THEME_FIELDS}
    org_obj = projected.get("organizationObj")
    if isinstance(org_obj, dict):
        projected["organizationObj"] = {k: v for k, v in org_obj.items() if k != "themeData"}
    return projected


class ThemeSyncError(RuntimeError):
    """不含凭据与敏感响应体的可安全输出异常。"""


def wrap_style(css_text: str) -> str:
    return f"<style>\n{css_text.strip()}\n</style>"


def load_patches(org_patch_path: Path = ORG_PATCH_PATH, app_patch_path: Path = APP_PATCH_PATH) -> tuple[dict, dict]:
    try:
        org_patch = json.loads(org_patch_path.read_text(encoding="utf-8"))
        app_patch = json.loads(app_patch_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ThemeSyncError("无法解析主题补丁文件") from exc

    if set(org_patch) != {"themeData"} or not isinstance(org_patch.get("themeData"), dict):
        raise ThemeSyncError("organization-theme.patch.json 只能包含 themeData 对象")
    if (
        set(app_patch) != APP_THEME_FIELDS
        or not isinstance(app_patch.get("themeData"), dict)
        or not isinstance(app_patch.get("formCss"), str)
        or not isinstance(app_patch.get("formCssMobile"), str)
    ):
        raise ThemeSyncError("application-theme.patch.json 只能包含 themeData、formCss、formCssMobile")
    return org_patch, app_patch


def prepare_backup_dir(backup_dir: Path) -> Path:
    requested = backup_dir.expanduser().absolute()
    if requested.is_symlink():
        raise ThemeSyncError("私密备份目录不能是软链接")
    resolved = requested.resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            check = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(resolved / "probe.private.json")],
                cwd=parent,
                capture_output=True,
                check=False,
            )
            if check.returncode != 0:
                raise ThemeSyncError("位于 Git 仓库内的备份目录必须被 .gitignore 忽略")
            break
    missing = []
    cur = resolved
    while not cur.exists():
        missing.append(cur)
        cur = cur.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    info = resolved.stat()
    if not resolved.is_dir() or info.st_uid != os.getuid() or (stat.S_IMODE(info.st_mode) & 0o077):
        raise ThemeSyncError("私密备份目录必须归属当前用户且权限为 0700")
    return resolved


def write_private_json(path: Path, payload: dict) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_http_caller(endpoint: str, client_id: str, client_secret: str):
    base = endpoint.rstrip("/")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(method: str, api_path: str, *, params: dict | None = None, body: dict | None = None):
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{base}/api/{api_path}{query}"
        headers = {
            "Authorization": f"Basic {basic}",
            "Accept-Language": "zh",
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(req, timeout=15) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ThemeSyncError(f"Casdoor 接口请求失败：{api_path}") from exc
        if not isinstance(parsed, dict) or parsed.get("status") != "ok":
            raise ThemeSyncError(f"Casdoor 拒绝操作：{api_path}")
        return parsed.get("data")

    return call


def _has_masked_secret(record: dict) -> bool:
    for value in record.values():
        if isinstance(value, str) and value and set(value) == {"*"}:
            return True
    return False


def sync_theme(
    call,
    *,
    app_names: tuple[str, ...] = DEFAULT_APPS,
    check_only: bool = False,
    backup_dir: Path | None = None,
    org_patch_path: Path = ORG_PATCH_PATH,
    app_patch_path: Path = APP_PATCH_PATH,
) -> dict:
    org_patch, app_patch = load_patches(org_patch_path, app_patch_path)

    org_orig = call("GET", "get-organization", params={"id": ORG_ID})
    if (
        not isinstance(org_orig, dict)
        or org_orig.get("owner") != "admin"
        or org_orig.get("name") != ORG_NAME
        or _has_masked_secret(org_orig)
        or not isinstance(org_orig.get("themeData") or {}, dict)
    ):
        raise ThemeSyncError("组织记录读取校验未通过（可能缺少管理权限或字段被打码）")

    app_originals: dict[str, dict] = {}
    for name in app_names:
        app_id = f"admin/{name}"
        rec = call("GET", "get-application", params={"id": app_id})
        if (
            not isinstance(rec, dict)
            or rec.get("owner") != "admin"
            or rec.get("name") != name
            or rec.get("organization") != ORG_NAME
            or not isinstance(rec.get("clientSecret"), str)
            or not rec["clientSecret"]
            or "*" in rec["clientSecret"]
            or _has_masked_secret(rec)
            or not isinstance(rec.get("themeData") or {}, dict)
        ):
            raise ThemeSyncError(f"应用 {app_id} 读取校验未通过（缺少管理权限或归属异常）")
        app_originals[name] = rec

    org_intended_theme = {**(org_orig.get("themeData") or {}), **org_patch["themeData"]}
    org_aligned = org_orig.get("themeData") == org_intended_theme

    apps_aligned: dict[str, bool] = {}
    app_intended: dict[str, dict] = {}
    for name, orig in app_originals.items():
        merged_theme = {**(orig.get("themeData") or {}), **app_patch["themeData"]}
        intended = {
            **orig,
            **app_patch,
            "themeData": merged_theme,
        }
        app_intended[name] = intended
        apps_aligned[name] = all(orig.get(k) == intended[k] for k in APP_THEME_FIELDS)

    if check_only:
        return {
            "aligned": org_aligned and all(apps_aligned.values()),
            "organization": {ORG_NAME: org_aligned},
            "applications": apps_aligned,
        }

    if backup_dir is None:
        raise ThemeSyncError("执行写入时必须指定 --backup-dir")

    root = prepare_backup_dir(backup_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_dir = root / f"swiss-clinical-v2-{stamp}"
    session_dir.mkdir(mode=0o700)

    write_private_json(session_dir / "organization-mabpharm.private.json", org_orig)
    for name, orig in app_originals.items():
        write_private_json(session_dir / f"application-{name}.private.json", orig)

    org_updated = False
    attempted_apps: list[str] = []
    try:
        org_body = {**org_orig, "themeData": org_intended_theme}
        org_updated = True
        call("POST", "update-organization", params={"id": ORG_ID}, body=org_body)
        org_actual = call("GET", "get-organization", params={"id": ORG_ID})
        if (
            not isinstance(org_actual, dict)
            or {k: v for k, v in org_actual.items() if k != "themeData"}
            != {k: v for k, v in org_orig.items() if k != "themeData"}
            or org_actual.get("themeData") != org_intended_theme
        ):
            raise ThemeSyncError("组织主题回读校验不一致")

        for name in app_names:
            app_id = f"admin/{name}"
            intended = app_intended[name]
            orig = app_originals[name]
            attempted_apps.append(name)
            call("POST", "update-application", params={"id": app_id}, body=intended)
            actual = call("GET", "get-application", params={"id": app_id})
            if (
                not isinstance(actual, dict)
                or _non_theme_app_projection(actual) != _non_theme_app_projection(orig)
                or any(actual.get(k) != intended[k] for k in APP_THEME_FIELDS)
            ):
                raise ThemeSyncError(f"应用 {app_id} 回读校验发现非主题字段变化")
    except ThemeSyncError as exc:
        rollback_ok = True
        if org_updated:
            try:
                call("POST", "update-organization", params={"id": ORG_ID}, body=org_orig)
                rollback_ok = (call("GET", "get-organization", params={"id": ORG_ID}) == org_orig) and rollback_ok
            except ThemeSyncError:
                rollback_ok = False
        for name in reversed(attempted_apps):
            app_id = f"admin/{name}"
            try:
                call("POST", "update-application", params={"id": app_id}, body=app_originals[name])
                rollback_ok = (call("GET", "get-application", params={"id": app_id}) == app_originals[name]) and rollback_ok
            except ThemeSyncError:
                rollback_ok = False
        write_private_json(session_dir / "receipt.private.json", {"completed": False, "rollback_verified": rollback_ok})
        if not rollback_ok:
            raise ThemeSyncError("主题同步失败且自动回滚未完全确认，请检查私密备份目录") from exc
        raise ThemeSyncError("主题同步失败，已恢复并校验原配置") from exc

    receipt = {
        "completed": True,
        "organization": ORG_NAME,
        "applications": list(app_names),
    }
    write_private_json(session_dir / "receipt.private.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="只检查线上/本地主题是否已对齐 Swiss Clinical v2")
    parser.add_argument("--backup-dir", type=Path, help="写入前保存原始配置的 0700 私密备份目录")
    parser.add_argument(
        "--apps",
        default=",".join(DEFAULT_APPS),
        help=f"逗号分隔的目标应用名列表（默认：{','.join(DEFAULT_APPS)}）",
    )
    args = parser.parse_args()
    os.umask(0o077)

    endpoint = os.environ.get("CASDOOR_ENDPOINT", "http://127.0.0.1:8000")
    try:
        client_id = os.environ["CASDOOR_CLIENT_ID"]
        client_secret = os.environ["CASDOOR_CLIENT_SECRET"]
    except KeyError as exc:
        sys.exit(f"缺少环境变量 {exc.args[0]}")

    apps = tuple(item.strip() for item in args.apps.split(",") if item.strip())
    if not apps:
        sys.exit("至少指定一个目标应用")

    caller = build_http_caller(endpoint, client_id, client_secret)
    try:
        result = sync_theme(caller, app_names=apps, check_only=args.check, backup_dir=args.backup_dir)
    except ThemeSyncError as exc:
        sys.exit(str(exc))

    print(json.dumps(result, ensure_ascii=False))
    if args.check and not result["aligned"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
