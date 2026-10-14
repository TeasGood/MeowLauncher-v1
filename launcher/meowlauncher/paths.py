import os
import sys

from . import APP

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
OS_NAME = "windows" if IS_WIN else ("osx" if IS_MAC else "linux")
IS_64 = sys.maxsize > 2 ** 32


def _default_root():
    env = os.environ.get("MEOW_HOME") or os.environ.get("MEOWCRAFT_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP)


ROOT = _default_root()


def P(*parts):
    return os.path.join(ROOT, *parts)


GAME = P("game")
VERSIONS = os.path.join(GAME, "versions")
LIBRARIES = os.path.join(GAME, "libraries")
ASSETS = os.path.join(GAME, "assets")
INSTANCES = P("instances")
RUNTIME = P("runtime")
CACHE = P("cache")
LANGDIR = P("lang")
CONFIG = P("config.json")
ACCOUNTS = P("accounts.json")
LOGS = P("logs")


def fs(path):
    if not IS_WIN:
        return path
    full = os.path.abspath(path)
    if len(full) < 240 or full.startswith("\\\\?\\"):
        return full
    if full.startswith("\\\\"):
        return "\\\\?\\UNC" + full[1:]
    return "\\\\?\\" + full


def ensure_dirs():
    for d in (ROOT, GAME, INSTANCES, RUNTIME, CACHE, LOGS):
        os.makedirs(d, exist_ok=True)


def legacy_root():
    old = _default_root().replace(APP, "MeowCraftLauncher")
    return old if old != ROOT and os.path.isdir(old) else None
