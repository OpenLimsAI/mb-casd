"""Offline contract tests for MBERP Swiss Clinical v2 Casdoor login theme assets and sync."""

import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apply_theme", ROOT / "scripts" / "apply_theme.py")
apply_theme = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_theme)


class SwissClinicalLoginThemeTests(unittest.TestCase):
    def test_css_enforces_swiss_clinical_v2_tokens(self):
        css = (ROOT / "assets" / "swiss-clinical-login.css").read_text(encoding="utf-8")
        for required_token in (
            "#1E466B",
            "#F6F8FA",
            "#FFFFFF",
            "1px solid #D8E0E8",
            "border-radius: 6px;",
            "border-radius: 4px;",
            "0 1px 2px rgba(15, 23, 42, 0.04)",
            "tabular-nums",
        ):
            self.assertIn(required_token, css, required_token)

        # Ensure legacy soft-card / v1 tokens are absent
        for legacy_token in ("#1a4f9c", "border-radius: 16px", "0 12px 38px"):
            self.assertNotIn(legacy_token.lower(), css.lower(), legacy_token)

    def test_patches_and_init_data_stay_in_exact_sync_with_css_source(self):
        css = (ROOT / "assets" / "swiss-clinical-login.css").read_text(encoding="utf-8").strip()
        expected_wrapped = f"<style>\n{css}\n</style>"

        org_patch, app_patch = apply_theme.load_patches()
        self.assertEqual(org_patch["themeData"]["colorPrimary"], "#1E466B")
        self.assertEqual(org_patch["themeData"]["borderRadius"], 6)
        self.assertEqual(app_patch["themeData"]["colorPrimary"], "#1E466B")
        self.assertEqual(app_patch["themeData"]["borderRadius"], 6)
        self.assertEqual(app_patch["formCss"], expected_wrapped)
        self.assertEqual(app_patch["formCssMobile"], expected_wrapped)

        seed = json.loads((ROOT / "init_data" / "init_data.json").read_text(encoding="utf-8"))
        org = seed["organizations"][0]
        app = seed["applications"][0]
        self.assertEqual(org["name"], "mabpharm")
        self.assertEqual(org["themeData"], org_patch["themeData"])
        self.assertEqual(app["name"], "mp-pm")
        self.assertEqual(app["themeData"], app_patch["themeData"])
        self.assertEqual(app["formCss"], expected_wrapped)
        self.assertEqual(app["formCssMobile"], expected_wrapped)

        # Verify auth / OIDC / PKCE seed invariants remain untouched
        self.assertTrue(app["enablePassword"])
        self.assertFalse(app["enableSignUp"])
        self.assertTrue(app["enablePkce"])
        self.assertEqual(app["grantTypes"], ["authorization_code", "refresh_token"])

    def test_sync_theme_preserves_auth_session_fields_and_writes_0600_backups(self):
        state = {
            "org": {
                "owner": "admin",
                "name": "mabpharm",
                "passwordType": "bcrypt",
                "languages": ["zh"],
                "themeData": {"themeType": "default", "colorPrimary": "#1a4f9c", "borderRadius": 8, "customFlag": True},
            },
            "apps": {
                "mp-pm": {
                    "owner": "admin",
                    "name": "mp-pm",
                    "organization": "mabpharm",
                    "clientId": "synthetic-id",
                    "clientSecret": "synthetic-secret-value",
                    "redirectUris": ["https://pm.openlims.ai/api/v1/auth/callback"],
                    "enablePkce": True,
                    "enableSigninSession": True,
                    "cookieExpireInHours": 168,
                    "themeData": {"retained": "yes", "colorPrimary": "#1a4f9c", "borderRadius": 8},
                    "formCss": "<style>.old{}</style>",
                    "formCssMobile": "<style>.old{}</style>",
                }
            },
        }
        original_snapshot = copy.deepcopy(state)

        def fake_call(method, path, *, params=None, body=None):
            target_id = params["id"]
            if path == "get-organization":
                self.assertEqual(target_id, "admin/mabpharm")
                return copy.deepcopy(state["org"])
            if path == "update-organization":
                state["org"] = copy.deepcopy(body)
                return "Affected"
            app_name = target_id.split("/", 1)[1]
            if path == "get-application":
                return copy.deepcopy(state["apps"][app_name])
            if path == "update-application":
                state["apps"][app_name] = copy.deepcopy(body)
                return "Affected"
            raise AssertionError(f"Unexpected path: {path}")

        pre_check = apply_theme.sync_theme(fake_call, app_names=("mp-pm",), check_only=True)
        self.assertFalse(pre_check["aligned"])

        with tempfile.TemporaryDirectory() as tmp:
            backup_root = Path(tmp) / "private-backups"
            receipt = apply_theme.sync_theme(fake_call, app_names=("mp-pm",), backup_dir=backup_root)
            self.assertTrue(receipt["completed"])
            self.assertEqual(stat.S_IMODE(backup_root.stat().st_mode), 0o700)
            for item in backup_root.rglob("*"):
                expected_mode = 0o700 if item.is_dir() else 0o600
                self.assertEqual(stat.S_IMODE(item.stat().st_mode), expected_mode)

        post_check = apply_theme.sync_theme(fake_call, app_names=("mp-pm",), check_only=True)
        self.assertTrue(post_check["aligned"])
        self.assertEqual(state["org"]["themeData"]["colorPrimary"], "#1E466B")
        self.assertEqual(state["org"]["themeData"]["borderRadius"], 6)
        self.assertTrue(state["org"]["themeData"]["customFlag"])

        updated_app = state["apps"]["mp-pm"]
        orig_app = original_snapshot["apps"]["mp-pm"]
        self.assertEqual(
            {k: v for k, v in updated_app.items() if k not in apply_theme.APP_THEME_FIELDS},
            {k: v for k, v in orig_app.items() if k not in apply_theme.APP_THEME_FIELDS},
        )
        self.assertEqual(updated_app["themeData"]["retained"], "yes")
        self.assertEqual(updated_app["themeData"]["colorPrimary"], "#1E466B")
        self.assertEqual(updated_app["themeData"]["borderRadius"], 6)

    def test_masked_secret_or_readback_tampering_aborts_and_rolls_back(self):
        base_org = {"owner": "admin", "name": "mabpharm", "themeData": {"colorPrimary": "#1a4f9c"}}
        base_app = {
            "owner": "admin",
            "name": "mp-pm",
            "organization": "mabpharm",
            "clientSecret": "***",
            "redirectUris": ["https://pm.openlims.ai/api/v1/auth/callback"],
            "themeData": {},
        }
        writes = []

        def masked_call(method, path, *, params=None, body=None):
            if method == "POST":
                writes.append(path)
            return copy.deepcopy(base_org if "organization" in path else base_app)

        with self.assertRaises(apply_theme.ThemeSyncError):
            apply_theme.sync_theme(masked_call, app_names=("mp-pm",), check_only=True)
        self.assertEqual(writes, [])

        # Now test automatic rollback if an update unexpectedly alters redirectUris
        state = {
            "org": copy.deepcopy(base_org),
            "app": {**copy.deepcopy(base_app), "clientSecret": "unmasked-secret"},
        }
        tamper_once = True

        def tampering_call(method, path, *, params=None, body=None):
            nonlocal tamper_once
            if path == "get-organization":
                return copy.deepcopy(state["org"])
            if path == "update-organization":
                state["org"] = copy.deepcopy(body)
                return "Affected"
            if path == "get-application":
                return copy.deepcopy(state["app"])
            if path == "update-application":
                state["app"] = copy.deepcopy(body)
                if tamper_once:
                    tamper_once = False
                    state["app"]["redirectUris"] = ["https://unexpected.invalid"]
                return "Affected"
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(apply_theme.ThemeSyncError, "已恢复并校验原配置"):
                apply_theme.sync_theme(tampering_call, app_names=("mp-pm",), backup_dir=Path(tmp) / "priv")
        self.assertEqual(state["org"], base_org)
        self.assertEqual(state["app"]["redirectUris"], ["https://pm.openlims.ai/api/v1/auth/callback"])


if __name__ == "__main__":
    unittest.main()
