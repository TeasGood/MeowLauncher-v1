import json
import locale
import os

from .lang import CATALOG

_current = "en"
_strings = {}
_fallback = {}


def _load_user_packs():
    from .paths import LANGDIR
    if not os.path.isdir(LANGDIR):
        return
    for name in sorted(os.listdir(LANGDIR)):
        if not name.endswith(".json"):
            continue
        code = name[:-5]
        try:
            with open(os.path.join(LANGDIR, name), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        strings = data.get("strings", data)
        entry = CATALOG.get(code, {})
        CATALOG[code] = {
            "native": data.get("native") or entry.get("native") or code,
            "english": data.get("english") or entry.get("english") or code,
            "strings": dict(entry.get("strings", {}), **strings),
        }


def init():
    global _fallback
    _load_user_packs()
    _fallback = CATALOG["en"]["strings"]


def languages():
    rows = [(code, v["native"], v["english"]) for code, v in CATALOG.items()]
    rows.sort(key=lambda r: (r[0] != "en", r[2].lower()))
    return rows


def has(code):
    return code in CATALOG


def current():
    return _current


def native_name(code):
    e = CATALOG.get(code)
    return e["native"] if e else code


def set_lang(code):
    global _current, _strings
    if code not in CATALOG:
        code = "en"
    _current = code
    _strings = CATALOG[code]["strings"]


def t(key, **kw):
    s = _strings.get(key) or _fallback.get(key) or key
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def plural(n, key_one, key_many):
    return t(key_one if n == 1 else key_many, n=n)


_ALIASES = {
    "zh_cn": "zh-Hans", "zh_sg": "zh-Hans", "zh_hans": "zh-Hans",
    "zh_tw": "zh-Hant", "zh_hk": "zh-Hant", "zh_mo": "zh-Hant", "zh_hant": "zh-Hant",
    "zh": "zh-Hans", "pt_br": "pt-BR", "pt": "pt-BR", "nb": "nb", "no": "nb",
    "nn": "nb", "in": "id", "iw": "he", "ji": "he", "sh": "sr", "bs": "sr",
    "mo": "ro", "tl": "fil", "cn": "zh-Hans",
}


def system_lang():
    raw = []
    for env in ("MEOW_LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        v = os.environ.get(env)
        if v:
            raw.extend(v.replace(":", ",").split(","))
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            n = ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
            if n:
                raw.append(buf.value)
        except Exception:
            pass
    try:
        loc = locale.getdefaultlocale()[0]
        if loc:
            raw.append(loc)
    except Exception:
        pass
    for item in raw:
        code = _normalize(item)
        if code:
            return code
    return "en"


def _normalize(item):
    item = item.split(".")[0].split("@")[0].strip().replace("-", "_")
    if not item or item.lower() in ("c", "posix"):
        return None
    low = item.lower()
    if low in _ALIASES and _ALIASES[low] in CATALOG:
        return _ALIASES[low]
    parts = low.split("_")
    base = parts[0]
    if len(parts) > 1:
        exact = base + "-" + parts[1].upper()
        if exact in CATALOG:
            return exact
        if low in _ALIASES and _ALIASES[low] in CATALOG:
            return _ALIASES[low]
    if base in _ALIASES and _ALIASES[base] in CATALOG:
        return _ALIASES[base]
    if base in CATALOG:
        return base
    for code in CATALOG:
        if code.split("-")[0] == base:
            return code
    return None
