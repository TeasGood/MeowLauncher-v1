from . import ar, be, bg, cs, da, de, el, en, es, fi, fr, he, hi, hu
from . import id as id_
from . import it, ja, kk, ko, nb, nl, pl, pt_BR, ro, ru, sk, sr, sv, th, tr, uk, vi
from . import zh_Hans, zh_Hant

_MODULES = {
    "en": en, "ru": ru, "uk": uk, "be": be, "kk": kk, "pl": pl, "cs": cs, "sk": sk,
    "de": de, "nl": nl, "fr": fr, "es": es, "pt-BR": pt_BR, "it": it, "ro": ro,
    "hu": hu, "el": el, "bg": bg, "sr": sr, "tr": tr, "sv": sv, "fi": fi, "da": da,
    "nb": nb, "zh-Hans": zh_Hans, "zh-Hant": zh_Hant, "ja": ja, "ko": ko, "vi": vi,
    "th": th, "id": id_, "hi": hi, "ar": ar, "he": he,
}

CODES = list(_MODULES)

CATALOG = {
    code: {"native": getattr(mod, "NATIVE", code),
           "english": getattr(mod, "ENGLISH", code),
           "strings": mod.STRINGS}
    for code, mod in _MODULES.items()
}


def missing(code):
    base = set(CATALOG["en"]["strings"])
    have = set(CATALOG.get(code, {}).get("strings", {}))
    return sorted(base - have)
