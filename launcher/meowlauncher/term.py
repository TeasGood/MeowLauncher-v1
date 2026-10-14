import os
import shutil
import sys
import unicodedata

from .paths import IS_WIN

_CODES = {
    "r": "\x1b[0m", "b": "\x1b[1m", "dim": "\x1b[2m", "it": "\x1b[3m",
    "rev": "\x1b[7m",
    "black": "\x1b[30m", "red": "\x1b[31m", "green": "\x1b[32m",
    "yellow": "\x1b[33m", "blue": "\x1b[34m", "magenta": "\x1b[35m",
    "cyan": "\x1b[36m", "white": "\x1b[37m", "grey": "\x1b[90m",
    "pink": "\x1b[95m", "lime": "\x1b[92m", "sky": "\x1b[96m",
    "orange": "\x1b[33m", "purple": "\x1b[35m",
}
_BG = {"purple": "\x1b[45m", "grey": "\x1b[100m", "sel": "\x1b[48;5;54m"}

ENABLED = True
UNICODE = True


def c(name):
    return _CODES.get(name, "") if ENABLED else ""


def bg(name):
    return _BG.get(name, "") if ENABLED else ""


def paint(text, *names):
    if not ENABLED or not names:
        return text
    return "".join(_CODES.get(n, "") for n in names) + text + _CODES["r"]


def set_color(enabled):
    global ENABLED
    ENABLED = bool(enabled)


def set_unicode(enabled):
    global UNICODE
    UNICODE = bool(enabled)


def color_auto():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def glyph(uni, ascii_):
    return uni if UNICODE else ascii_


def _w(ch):
    if ch == "\t":
        return 4
    o = ord(ch)
    if o < 32 or 0x200B <= o <= 0x200F or o == 0xFEFF:
        return 0
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def wlen(s):
    return sum(_w(ch) for ch in strip_ansi(s))


def strip_ansi(s):
    out, i, n = [], 0, len(s)
    while i < n:
        if s[i] == "\x1b":
            j = i + 1
            if j < n and s[j] == "[":
                j += 1
                while j < n and not ("@" <= s[j] <= "~"):
                    j += 1
            i = j + 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def fit(s, width, ellipsis=None):
    if width <= 0:
        return ""
    if wlen(s) <= width:
        return s
    ell = ellipsis if ellipsis is not None else glyph("…", "...")
    ew = wlen(ell)
    if width <= ew:
        return ell[:width]
    acc, cur = [], 0
    for ch in s:
        w = _w(ch)
        if cur + w > width - ew:
            break
        acc.append(ch)
        cur += w
    return "".join(acc) + ell


def pad(s, width, align="<"):
    s = fit(s, width)
    gap = max(0, width - wlen(s))
    if align == ">":
        return " " * gap + s
    if align == "^":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def size():
    try:
        sz = shutil.get_terminal_size((80, 24))
        return max(40, sz.columns), max(10, sz.lines)
    except Exception:
        return 80, 24


def init():
    if IS_WIN:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleOutputCP(65001)
            k.SetConsoleCP(65001)
            h = k.GetStdHandle(-11)
            m = ctypes.c_uint()
            k.GetConsoleMode(h, ctypes.byref(m))
            k.SetConsoleMode(h, m.value | 0x0004)
        except Exception:
            pass
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf" not in enc:
        set_unicode(False)


def write(s=""):
    sys.stdout.write(s)


def out(s=""):
    sys.stdout.write(s + "\n")


def flush():
    sys.stdout.flush()


def clear():
    sys.stdout.write("\x1b[2J\x1b[H" if ENABLED else "\n" * 3)


def home():
    sys.stdout.write("\x1b[H")


def cursor(show):
    if ENABLED:
        sys.stdout.write("\x1b[?25h" if show else "\x1b[?25l")
        flush()


def alt_screen(on):
    if ENABLED:
        sys.stdout.write("\x1b[?1049h" if on else "\x1b[?1049l")
        flush()


KEY_NAMES = {"up", "down", "left", "right", "enter", "esc", "backspace",
             "tab", "home", "end", "pgup", "pgdn", "del"}


_LAYOUT = {}


def _layout(source, latin_row):
    for src, dst in zip(source, latin_row):
        _LAYOUT.setdefault(src, dst)


_layout("ёйцукенгшщзхъ", "`qwertyuiop[]")
_layout("фывапролджэ", "asdfghjkl;'")
_layout("ячсмитьбю.", "zxcvbnm,./")
_layout("іїєў", "s]'o")
_layout("ςερτυθιοπ", "wertyuiop")
_layout("ασδφγηξκλ", "asdfghjkl")
_layout("ζχψωβνμ", "zxcvbnm")
_layout("קראטוןםפ", "ertyuiop")
_layout("שדגכעיחלך", "asdfghjkl")
_layout("זסבהנמצ", "zxcvbnm")


def latin(key):
    if not key or len(key) != 1:
        return key
    low = key.lower()
    return _LAYOUT.get(low, low)


def wait_key(timeout):
    import time
    end = time.time() + timeout
    while True:
        if kbhit():
            return getkey()
        if time.time() >= end:
            return None
        time.sleep(0.03)


def kbhit():
    if IS_WIN:
        import msvcrt
        return msvcrt.kbhit()
    import select
    try:
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False


def getkey():
    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            n = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right",
                    "G": "home", "O": "end", "I": "pgup", "Q": "pgdn",
                    "S": "del"}.get(n, "")
        if ch == "\r":
            return "enter"
        if ch == "\x1b":
            return "esc"
        if ch in ("\x08", "\x7f"):
            return "backspace"
        if ch == "\t":
            return "tab"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            if select.select([fd], [], [], 0.06)[0]:
                seq = os.read(fd, 16)
                m = {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
                     b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left",
                     b"[H": "home", b"[F": "end", b"[5": "pgup", b"[6": "pgdn",
                     b"[3": "del"}
                return m.get(seq[:2], "")
            return "esc"
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch in (b"\x7f", b"\x08"):
            return "backspace"
        if ch == b"\t":
            return "tab"
        if ch == b"\x03":
            raise KeyboardInterrupt
        if ch == b"\x04":
            return "esc"
        first = ch[0]
        extra = 1 if 0xC0 <= first < 0xE0 else 2 if 0xE0 <= first < 0xF0 else 3 if first >= 0xF0 else 0
        if extra:
            ch += os.read(fd, extra)
        try:
            return ch.decode("utf-8")
        except Exception:
            return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
