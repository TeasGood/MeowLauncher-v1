import hashlib
import json
import time
import urllib.parse
import uuid

from . import net
from .i18n import t

TENANT = "consumers"
DEVICE_CODE_URL = "https://login.microsoftonline.com/%s/oauth2/v2.0/devicecode" % TENANT
TOKEN_URL = "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % TENANT
SCOPE = "XboxLive.signin offline_access"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

OFFLINE = "offline"
MICROSOFT = "microsoft"


class AuthError(RuntimeError):
    pass


class Cancelled(Exception):
    pass


def offline_uuid(nick):
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + nick).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def make_offline(nick):
    return {
        "id": "offline:" + nick.lower(),
        "type": OFFLINE,
        "name": nick,
        "uuid": offline_uuid(nick),
        "xuid": "",
        "access_token": "0",
        "refresh_token": "",
        "expires_at": 0,
    }


def valid_nick(nick):
    if not 3 <= len(nick) <= 16:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in nick)


def request_device_code(client_id):
    status, data = net.post_json(DEVICE_CODE_URL,
                                 {"client_id": client_id, "scope": SCOPE}, form=True)
    if status != 200 or "device_code" not in data:
        raise AuthError(_oauth_error(data))
    return data


def poll_token(client_id, device, should_cancel=None):
    interval = max(1, int(device.get("interval", 5)))
    deadline = time.time() + int(device.get("expires_in", 900))
    payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device["device_code"],
    }
    while time.time() < deadline:
        for _ in range(interval * 10):
            if should_cancel and should_cancel():
                raise Cancelled()
            time.sleep(0.1)
        status, data = net.post_json(TOKEN_URL, payload, form=True)
        if status == 200 and data.get("access_token"):
            return data
        err = data.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 2
            continue
        if err == "expired_token":
            raise AuthError(t("accs.ms.timeout"))
        if err in ("authorization_declined", "access_denied"):
            raise AuthError(t("accs.ms.denied"))
        raise AuthError(_oauth_error(data))
    raise AuthError(t("accs.ms.timeout"))


def _oauth_error(data):
    desc = data.get("error_description") or data.get("error") or data.get("raw") or ""
    return str(desc).split("\r")[0][:300] or t("err.unknown")


def _xbox_login(ms_access_token):
    status, data = net.post_json(XBL_URL, {
        "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                       "RpsTicket": "d=" + ms_access_token},
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    })
    if status != 200 or "Token" not in data:
        raise AuthError(t("accs.ms.noxbox"))
    uhs = data["DisplayClaims"]["xui"][0]["uhs"]
    return data["Token"], uhs


def _xsts(xbl_token):
    status, data = net.post_json(XSTS_URL, {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    })
    if status == 401:
        xerr = str(data.get("XErr", ""))
        if xerr == "2148916233":
            raise AuthError(t("accs.ms.noxbox"))
        if xerr in ("2148916238", "2148916236"):
            raise AuthError(t("accs.ms.child"))
        raise AuthError(data.get("Message") or t("accs.ms.denied"))
    if status != 200 or "Token" not in data:
        raise AuthError(t("accs.ms.denied"))
    return data["Token"], data["DisplayClaims"]["xui"][0]["uhs"]


def _minecraft_token(uhs, xsts_token):
    status, data = net.post_json(MC_LOGIN_URL,
                                 {"identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts_token)})
    if status != 200 or not data.get("access_token"):
        raise AuthError(t("accs.ms.nogame"))
    return data["access_token"], int(data.get("expires_in", 86400))


def _profile(mc_token):
    try:
        raw = net.get_bytes(MC_PROFILE_URL, headers={"Authorization": "Bearer " + mc_token})
    except Exception:
        raise AuthError(t("accs.ms.nogame"))
    data = json.loads(raw.decode("utf-8"))
    if not data.get("id"):
        raise AuthError(t("accs.ms.nogame"))
    raw_id = data["id"]
    return data["name"], str(uuid.UUID(hex=raw_id))


def _finish(ms_tokens):
    xbl_token, _uhs = _xbox_login(ms_tokens["access_token"])
    xsts_token, uhs = _xsts(xbl_token)
    mc_token, lifetime = _minecraft_token(uhs, xsts_token)
    name, player_uuid = _profile(mc_token)
    return {
        "id": "microsoft:" + player_uuid,
        "type": MICROSOFT,
        "name": name,
        "uuid": player_uuid,
        "xuid": uhs,
        "access_token": mc_token,
        "refresh_token": ms_tokens.get("refresh_token", ""),
        "expires_at": int(time.time() + lifetime - 60),
    }


def login_url(device):
    complete = device.get("verification_uri_complete")
    if complete:
        return complete
    base = device.get("verification_uri") or device.get("verification_url") or ""
    code = device.get("user_code") or ""
    if not base or not code:
        return base
    joiner = "&" if "?" in base else "?"
    return base + joiner + "otc=" + urllib.parse.quote(code)


def login_microsoft(client_id, on_code, should_cancel=None):
    if not client_id:
        raise AuthError(t("accs.ms.noid"))
    device = request_device_code(client_id)
    on_code(device.get("verification_uri") or device.get("verification_url", ""),
            device["user_code"], login_url(device))
    tokens = poll_token(client_id, device, should_cancel)
    return _finish(tokens)


def refresh(account, client_id):
    if account.get("type") != MICROSOFT:
        return account
    if account.get("expires_at", 0) > time.time():
        return account
    if not account.get("refresh_token") or not client_id:
        raise AuthError(t("accs.expired"))
    status, data = net.post_json(TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": account["refresh_token"],
        "scope": SCOPE,
    }, form=True)
    if status != 200 or not data.get("access_token"):
        raise AuthError(t("accs.expired"))
    fresh = _finish(data)
    fresh["id"] = account["id"]
    if not fresh.get("refresh_token"):
        fresh["refresh_token"] = account["refresh_token"]
    return fresh


def is_expired(account):
    return (account.get("type") == MICROSOFT
            and account.get("expires_at", 0) <= time.time())
