#!/usr/bin/env python3
"""Server-only isolated IAM contract validation; never target production identities.

Requires the dedicated labelled validation network/containers and a 0600
private.json created by the operator in ~/security-iam-validation-20261102.
All generated passwords and private diagnostic payloads remain on the server.
"""

import base64
import copy
import crypt
import hashlib
import http.cookiejar
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

os.umask(0o077)
root = Path.home() / "security-iam-validation-20261102"
endpoint = (root / "endpoint").read_text().strip()
# This verifier is intentionally tied to the dedicated synthetic environment.
# A missing label, a published port, a different endpoint, or production network
# refuses all writes before reading test credentials.
container = json.loads(
    subprocess.check_output(["docker", "inspect", "maibo-iam-security-20261102"])
)[0]
network_name = "maibo-iam-security-20261102"
assert (
    container["Config"]["Labels"].get("purpose") == "maibo-iam-security-validation"
), "Not a synthetic validation container"
assert not container["HostConfig"].get(
    "PortBindings"
), "Public port binding is forbidden"
assert set(container["NetworkSettings"]["Networks"]) == {
    network_name
}, "Unexpected network attachment"
network = json.loads(
    subprocess.check_output(["docker", "network", "inspect", network_name])
)[0]
assert network["Internal"] is True, "Validation network must be isolated"
expected = (
    "http://"
    + container["NetworkSettings"]["Networks"][network_name]["IPAddress"]
    + ":8000"
)
assert endpoint == expected, "Endpoint does not match the synthetic container"
private = json.loads((root / "private.json").read_text())


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.jar),
        )

    def call(self, path, method="GET", data=None, form=None, params=None, basic=None):
        headers = {"Accept-Language": "en", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode()
        elif form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            payload = urllib.parse.urlencode(form).encode()
        else:
            payload = None
        if basic:
            headers["Authorization"] = (
                "Basic "
                + base64.b64encode(
                    (basic["clientId"] + ":" + basic["clientSecret"]).encode()
                ).decode()
            )
        request = urllib.request.Request(
            endpoint + path + ("?" + urllib.parse.urlencode(params) if params else ""),
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=20) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
        try:
            return json.loads(body)
        except Exception:
            raise RuntimeError("Non-JSON response on " + path)

    def ok(self, path, **kwargs):
        result = self.call("/api/" + path, **kwargs)
        if result.get("status") != "ok":
            # Full diagnostic payload stays private on the server; never print secrets.
            (root / "last-error.private.json").write_text(
                json.dumps({"path": path, "result": result})
            )
            raise RuntimeError("IAM API failed: " + path + "; private diagnostic saved")
        return result

    def login(self, org, user, password, app="app-built-in", kind="login", params=None):
        return self.ok(
            "login",
            method="POST",
            data={
                "organization": org,
                "username": user,
                "password": password,
                "application": app,
                "type": kind,
                "autoSignin": True,
                "signinMethod": "Password",
            },
            params=params,
        )


def save_private():
    (root / "private.json").write_text(json.dumps(private))
    (root / "private.json").chmod(0o600)


def initialize():
    admin = Client()
    for _ in range(40):
        try:
            admin.login(
                "built-in",
                "admin",
                private["admin_password"]
                if private.get("initialized_admin")
                else "123",
            )
            break
        except (OSError, RuntimeError):
            time.sleep(1)
    else:
        raise RuntimeError("Candidate IAM login not ready; inspect private log")
    if not private.get("initialized_admin"):
        admin.ok(
            "set-password",
            method="POST",
            form={
                "userOwner": "built-in",
                "userName": "admin",
                "oldPassword": "123",
                "newPassword": private["admin_password"],
            },
        )
        private["initialized_admin"] = True
        save_private()
        admin = Client()
        admin.login("built-in", "admin", private["admin_password"])
    org = admin.ok("get-organization", params={"id": "admin/built-in"})["data"]
    org.update(
        name="security-validation",
        displayName="Synthetic Security Validation",
        enableTour=False,
        passwordOptions=["AtLeast6"],
    )
    admin.ok("add-organization", method="POST", data=org)
    template = admin.ok("get-application", params={"id": "admin/app-built-in"})["data"]
    template["enableSignUp"] = False
    template["providers"] = []
    admin.ok(
        "update-application",
        method="POST",
        params={"id": "admin/app-built-in"},
        data=template,
    )
    apps = []
    for label in ["a", "b"]:
        app = copy.deepcopy(template)
        app.update(
            name="security-validation-" + label,
            displayName="Synthetic Validation " + label,
            organization=org["name"],
            clientId=secrets.token_hex(12),
            clientSecret=secrets.token_urlsafe(32),
            grantTypes=["authorization_code", "password", "refresh_token"],
            enableSigninSession=True,
            enableConsent=False,
            redirectUris=["http://test-client.invalid/callback"],
            expireInHours=1,
            refreshExpireInHours=24,
            tokenFormat="JWT",
            cookieExpireInHours=1,
        )
        admin.ok("add-application", method="POST", data=app)
        apps.append(app)
    private["apps"] = apps
    private["users"] = {}
    for user in ["alice", "bob"]:
        password = secrets.token_urlsafe(24) + "Aa1!"
        private["users"][user] = password
        admin.ok(
            "add-user",
            method="POST",
            data={
                "owner": org["name"],
                "name": user,
                "displayName": "Synthetic " + user,
                "password": password,
                "type": "normal-user",
                "email": user + "@example.invalid",
                "signupApplication": apps[0]["name"],
            },
        )
    private["initialized"] = True
    save_private()
    print(
        "Synthetic organization, two applications and two isolated users initialized; default admin password replaced"
    )
    return admin


def token_session(user, app):
    c = Client()
    verifier = secrets.token_urlsafe(40)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    params = {
        "clientId": app["clientId"],
        "responseType": "code",
        "redirectUri": "http://test-client.invalid/callback",
        "scope": "openid profile email",
        "state": secrets.token_hex(16),
        "nonce": secrets.token_hex(16),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    code = c.login(
        "security-validation", user, private["users"][user], app["name"], "code", params
    )["data"]
    token = c.call(
        "/api/login/oauth/access_token",
        method="POST",
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://test-client.invalid/callback",
            "code_verifier": verifier,
        },
        basic=app,
    )
    if not token.get("access_token") or not token.get("refresh_token"):
        (root / "last-error.private.json").write_text(
            json.dumps({"path": "code-exchange", "result": token})
        )
        raise RuntimeError("Code exchange failed; private diagnostic saved")
    return c, token


def introspect(token, app):
    return Client().call(
        "/api/login/oauth/introspect",
        method="POST",
        form={"token": token, "token_type_hint": "access_token"},
        basic=app,
    )


def refresh(token, app):
    return Client().call(
        "/api/login/oauth/access_token",
        method="POST",
        form={"grant_type": "refresh_token", "refresh_token": token},
        basic=app,
    )


def quick_login(c, app):
    return c.call(
        "/api/login",
        method="POST",
        data={"application": app["name"], "type": "login", "autoSignin": True},
    )


def main():
    if not private.get("initialized"):
        admin = initialize()
    else:
        admin = Client()
        admin.login("built-in", "admin", private["admin_password"])
    # Reset the synthetic fixture only, so a previous interrupted assertion can be rerun.
    private["users"]["alice"] = secrets.token_urlsafe(24) + "Aa1!"
    admin.ok(
        "set-password",
        method="POST",
        form={
            "userOwner": "security-validation",
            "userName": "alice",
            "newPassword": private["users"]["alice"],
        },
    )
    save_private()
    results = []
    for scenario in ("self-set-password", "admin-set-password", "columns-password"):
        apps = private["apps"]
        sessions = [token_session("alice", app) for app in apps]
        bob, bob_token = token_session("bob", apps[0])
        assert all(
            introspect(t["access_token"], app).get("active") is True
            for (_, t), app in zip(sessions, apps)
        ), "Baseline access inactive"
        assert (
            quick_login(sessions[0][0], apps[1]).get("status") == "ok"
        ), "Baseline SSO failed"
        # Include one refreshed token so revocation covers the rotated chain too.
        rotated = refresh(sessions[0][1]["refresh_token"], apps[0])
        if not rotated.get("access_token"):
            (root / "last-error.private.json").write_text(
                json.dumps({"path": "refresh", "result": rotated})
            )
            raise RuntimeError("Baseline refresh failed")
        old = private["users"]["alice"]
        new = secrets.token_urlsafe(24) + "Aa1!"
        if scenario == "self-set-password":
            sessions[0][0].ok(
                "set-password",
                method="POST",
                form={
                    "userOwner": "security-validation",
                    "userName": "alice",
                    "oldPassword": old,
                    "newPassword": new,
                },
            )
        elif scenario == "admin-set-password":
            admin.ok(
                "set-password",
                method="POST",
                form={
                    "userOwner": "security-validation",
                    "userName": "alice",
                    "newPassword": new,
                },
            )
        else:
            admin.ok(
                "update-user",
                method="POST",
                params={"id": "security-validation/alice", "columns": "password"},
                # Upstream columns=password is a storage-format import API, not
                # the native plaintext set-password endpoint.
                data={
                    "password": crypt.crypt(new, crypt.mksalt(crypt.METHOD_BLOWFISH))
                },
            )
        private["users"]["alice"] = new
        save_private()
        for (_, token), app in zip(sessions, apps):
            assert introspect(token["access_token"], app).get("active") is False, (
                scenario + ": old access still active"
            )
            assert (
                refresh(token["refresh_token"], app).get("error") == "invalid_grant"
            ), scenario + ": old refresh not rejected"
        assert introspect(rotated["access_token"], apps[0]).get("active") is False, (
            scenario + ": rotated access active"
        )
        assert (
            refresh(rotated["refresh_token"], apps[0]).get("error") == "invalid_grant"
        ), scenario + ": rotated refresh not rejected"
        for c, _ in sessions:
            assert quick_login(c, apps[1]).get("status") != "ok", (
                scenario + ": old SSO retained"
            )
        assert introspect(bob_token["access_token"], apps[0]).get("active") is True, (
            scenario + ": other user affected"
        )
        assert quick_login(bob, apps[1]).get("status") == "ok", (
            scenario + ": other SSO affected"
        )
        assert quick_login(admin, private["apps"][0]).get("status") == "ok", (
            scenario + ": admin session affected"
        )
        fresh = Client()
        fresh.login("security-validation", "alice", new, apps[0]["name"])
        result = {
            "scenario": scenario,
            "access_revoked": True,
            "refresh_revoked": True,
            "rotated_chain_revoked": True,
            "both_sso_sessions_revoked": True,
            "other_user_unchanged": True,
            "admin_session_preserved": True,
            "new_password_login": True,
        }
        results.append(result)
        print(scenario + ": all seven security assertions passed", flush=True)
    admin.ok(
        "update-user",
        method="POST",
        params={"id": "security-validation/alice", "columns": "needUpdatePassword"},
        data={"needUpdatePassword": True},
    )
    temporary = Client()
    login = temporary.login(
        "security-validation",
        "alice",
        private["users"]["alice"],
        private["apps"][0]["name"],
    )
    assert login.get("data3") is True, "Temporary password flag missing at native login"
    new = secrets.token_urlsafe(24) + "Aa1!"
    temporary.ok(
        "set-password",
        method="POST",
        form={
            "userOwner": "security-validation",
            "userName": "alice",
            "oldPassword": private["users"]["alice"],
            "newPassword": new,
        },
    )
    private["users"]["alice"] = new
    save_private()
    after = admin.ok("get-user", params={"id": "security-validation/alice"})["data"]
    assert (
        after.get("needUpdatePassword") is False
    ), "Temporary password flag not cleared"
    results.append(
        {
            "scenario": "native-temporary-password",
            "flag_reported_at_login": True,
            "cleared_after_change": True,
        }
    )
    (root / "results.json").write_text(json.dumps(results, indent=2))
    print(
        "Native temporary password flag and completion passed; sanitized results saved server-side"
    )


if __name__ == "__main__":
    main()
