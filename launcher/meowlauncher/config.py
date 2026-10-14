import json
import os

from . import paths

BUILTIN_MS_CLIENT_ID = ""

SHOW_MICROSOFT = False
SHOW_CURSEFORGE = False

DEFAULTS = {
    "lang": None,
    "ram_mb": 4096,
    "color": True,
    "threads": 12,
    "java_path": "",
    "cf_key": "",
    "ms_client_id": BUILTIN_MS_CLIENT_ID,
    "last_instance": "",
    "show_snapshots": False,
    "keep_log": True,
}

RAM_CHOICES = [1024, 2048, 3072, 4096, 6144, 8192, 12288, 16384]


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    if private and os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


class Config(dict):
    def __init__(self):
        super(Config, self).__init__(DEFAULTS)
        self.update({k: v for k, v in _read(paths.CONFIG, {}).items() if k in DEFAULTS})
        if not self["ms_client_id"]:
            self["ms_client_id"] = BUILTIN_MS_CLIENT_ID
        env_id = os.environ.get("MEOW_MS_CLIENT_ID")
        if env_id:
            self["ms_client_id"] = env_id
        env_cf = os.environ.get("MEOW_CF_KEY")
        if env_cf:
            self["cf_key"] = env_cf

    def save(self):
        _write(paths.CONFIG, dict(self))


def load():
    return Config()


def load_accounts():
    data = _read(paths.ACCOUNTS, {})
    accounts = data.get("accounts") or []
    return {"active": data.get("active", ""), "accounts": accounts}


def save_accounts(store):
    _write(paths.ACCOUNTS, store, private=True)
