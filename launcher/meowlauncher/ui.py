from . import APP, VERSION
from . import term
from .i18n import t

PALETTE = [
    ("purple", 141), ("pink", 213), ("red", 203), ("orange", 215),
    ("yellow", 222), ("lime", 156), ("green", 114), ("teal", 80),
    ("cyan", 123), ("blue", 111), ("sand", 180), ("white", 252),
]
PALETTE_BASIC = {
    "purple": "magenta", "pink": "magenta", "red": "red", "orange": "yellow",
    "yellow": "yellow", "lime": "green", "green": "green", "teal": "cyan",
    "cyan": "cyan", "blue": "blue", "sand": "yellow", "white": "white",
}
DEFAULT_COLOR = "purple"


def color_code(name):
    if not term.ENABLED:
        return ""
    for key, code in PALETTE:
        if key == name:
            return "\x1b[38;5;%dm" % code
    return term.c(PALETTE_BASIC.get(name, "magenta"))


def cat(color=DEFAULT_COLOR):
    return color_code(color) + term.glyph("●", "*") + term.c("r")


def dim(s):
    return term.c("dim") + s + term.c("r")


class Row(object):
    __slots__ = ("label", "sub", "color", "badge", "value", "dimmed")

    def __init__(self, label, sub="", color=None, badge="", value=None, dimmed=False):
        self.label = label
        self.sub = sub
        self.color = color
        self.badge = badge
        self.value = value
        self.dimmed = dimmed


def header_lines(sub=""):
    purple = color_code(DEFAULT_COLOR)
    first = (purple + " /\\_/\\ " + term.c("r") + "  " + term.c("b") + APP + term.c("r")
             + dim(" " + VERSION))
    second = purple + "( o.o )" + term.c("r")
    if sub:
        second += "  " + dim(term.fit(sub, max(10, term.size()[0] - 12)))
    return [first, second]


def header(sub=""):
    for line in header_lines(sub):
        term.out(line)


def frame(title, sub="", body=None, footer=""):
    cols, rows = term.size()
    head = header_lines(sub) + [""]
    if title:
        head.append(" " + term.c("b") + term.fit(title, cols - 2) + term.c("r"))
        head.append("")
    foot = []
    if footer:
        foot = [""] + [dim(l) for l in _wrap_hints(footer, cols - 1)]
    lines = [term.fit(l, cols - 1) for l in (body or [])]
    budget = rows - len(head) - len(foot)
    if len(lines) > budget:
        lines = lines[:max(0, budget)]
    _paint(head + lines + foot)


def _paint(lines):
    if not term.ENABLED:
        term.clear()
        for line in lines:
            term.out(line)
        term.flush()
        return
    out = ["\x1b[H"]
    for line in lines:
        out.append(line + "\x1b[K\n")
    out.append("\x1b[J")
    term.write("".join(out))
    term.flush()


def _wrap_hints(footer, width):
    lines = []
    for raw in footer.split("\n"):
        parts, cur = raw.split("  "), ""
        for part in parts:
            probe = (cur + "  " + part) if cur else part
            if term.wlen(probe) > width and cur:
                lines.append(cur)
                cur = part
            else:
                cur = probe
        lines.append(term.fit(cur, width))
    return lines


def hints(*pairs):
    parts = ["[%s] %s" % (k, v) for k, v in pairs if v]
    return "  ".join(parts)


def render_row(row, width, selected):
    mark = term.glyph("▸ ", "> ") if selected else "  "
    left = ""
    if row.color:
        left += cat(row.color) + " "
    name = row.label
    if row.badge:
        name += " " + row.badge
    inner = width - 2
    name_w = term.wlen(term.strip_ansi(left))
    sub = row.sub or ""
    sub_w = term.wlen(sub)
    room = inner - name_w - 2
    if sub and room - sub_w >= 12:
        name_room = room - sub_w - 1
        body = term.pad(term.fit(name, name_room), name_room) + " " + dim(sub)
    elif sub and room >= 18:
        half = max(10, room * 2 // 3)
        body = term.pad(term.fit(name, half), half) + " " + dim(term.fit(sub, room - half - 1))
    else:
        body = term.fit(name, max(1, room))
    if selected:
        body = term.c("b") + body + term.c("r")
    elif row.dimmed:
        body = dim(body)
    return mark + left + body


def _viewport(total, sel, height):
    if total <= height:
        return 0, total
    top = max(0, min(sel - height // 2, total - height))
    return top, top + height


def select(title, rows, sel=0, sub="", search=None, keys=None, footer_extra="",
           empty=None, query="", pick_label=None, fetch=None, busy="", note=""):
    keys = keys or {}
    typing = search == "always"
    pending = False
    fetching = False
    while True:
        cols, lines = term.size()
        flt = list(rows) if fetch else [r for r in rows if not query or _match(query, r)]
        sel = max(0, min(sel, len(flt) - 1)) if flt else 0

        pairs = [("Enter", pick_label or t("ui.pick")),
                 (term.glyph("↑↓", "^v"), t("ui.move"))]
        if search == "slash" and not query:
            pairs.append(("/", t("search")))
        for k, label in keys.items():
            pairs.append((k.upper(), label))
        pairs.append(("Esc", t("ui.back")))
        foot = hints(*pairs)
        if footer_extra:
            foot = foot + "   " + footer_extra

        shown = busy if fetching else ("" if pending else note)
        reserved = (6 + len(_wrap_hints(foot, cols - 1)) + (2 if (typing or query) else 0)
                    + (2 if shown else 0) + 2)
        height = max(3, lines - reserved)
        top, bottom = _viewport(len(flt), sel, height)
        body = []
        if typing or query:
            cursor = term.glyph("▏", "_") if typing else ""
            body.append(" " + dim(t("search") + ": ") + query + cursor)
            body.append("")
        if shown:
            body.append("  " + dim(shown))
            body.append("")
        if not flt and not fetching:
            body.append("  " + dim(empty or t("empty")))
        for i in range(top, bottom):
            body.append(render_row(flt[i], cols - 1, i == sel))
        if len(flt) > height:
            body.append("")
            body.append("  " + dim(t("ui.of", i=sel + 1, n=len(flt))))
        frame(title, sub, body, foot)

        if fetching:
            fetching = False
            rows, note = fetch(query)
            sel = 0
            continue
        if pending:
            k = term.wait_key(0.35)
            if k is None:
                pending = False
                fetching = True
                continue
        else:
            k = term.getkey()
        alt = term.latin(k)
        if k in ("up",) or (not typing and alt == "k"):
            sel -= 1
            if sel < 0:
                sel = max(0, len(flt) - 1)
        elif k in ("down",) or (not typing and alt == "j"):
            sel += 1
            if sel >= len(flt):
                sel = 0
        elif k == "pgup":
            sel = max(0, sel - height)
        elif k == "pgdn":
            sel = min(len(flt) - 1, sel + height) if flt else 0
        elif k == "home":
            sel = 0
        elif k == "end":
            sel = max(0, len(flt) - 1)
        elif k == "enter":
            if flt:
                return "pick", rows.index(flt[sel]), None
        elif k == "esc":
            if query:
                query, typing = "", search == "always"
                fetching = fetch is not None
                continue
            return "back", -1, None
        elif k == "backspace":
            if query:
                query = query[:-1]
                pending = fetch is not None
            elif not typing:
                return "back", -1, None
        elif alt == "/" and search == "slash" and not typing:
            typing = True
        elif typing and len(k) == 1 and k not in term.KEY_NAMES and k.isprintable():
            query += k
            sel = 0
            pending = fetch is not None
        elif not typing and len(k) == 1 and alt in keys:
            return "key", (rows.index(flt[sel]) if flt else -1), alt
        elif not typing and alt == "q":
            return "back", -1, None


def _match(query, row):
    hay = (row.label + " " + (row.sub or "")).lower()
    return all(part in hay for part in query.lower().split())


def ask(title, value="", sub="", hint="", allowed=None, maxlen=120, secret=False):
    buf = value
    while True:
        cols = term.size()[0]
        shown = ("*" * len(buf)) if secret else buf
        body = ["", "  " + term.fit(shown, cols - 6) + term.c("b")
                + term.glyph("▏", "_") + term.c("r")]
        if hint:
            body += ["", "  " + dim(hint)]
        frame(title, sub, body, hints(("Enter", t("save")), ("Esc", t("cancel"))))
        k = term.getkey()
        if k == "enter":
            return buf
        if k == "esc":
            return None
        if k == "backspace":
            buf = buf[:-1]
        elif len(k) == 1 and k.isprintable() and len(buf) < maxlen:
            if allowed is None or allowed(k):
                buf += k


def confirm(question, sub=""):
    rows = [Row(t("no")), Row(t("yes"))]
    action, idx, _key = select(question, rows, sel=0, sub=sub)
    return action == "pick" and idx == 1


def message(title, text, sub="", kind="info"):
    cols = term.size()[0]
    body = []
    paint = term.c("red") if kind == "error" else (term.c("green") if kind == "ok" else "")
    for line in str(text).split("\n"):
        for chunk in _wrap(line, cols - 4):
            body.append("  " + paint + chunk + term.c("r"))
    frame(title, sub, body, t("ui.anykey"))
    term.getkey()


def error(text, sub=""):
    message(t("error"), text, sub, kind="error")


def toast(text, kind="ok"):
    paint = term.c("green") if kind == "ok" else term.c("yellow")
    term.out(paint + term.fit("  " + text, term.size()[0] - 1) + term.c("r"))
    term.flush()


def _wrap(text, width):
    if width <= 0:
        return [text]
    words, line, out = text.split(" "), "", []
    for w in words:
        probe = (line + " " + w).strip()
        if term.wlen(probe) > width and line:
            out.append(line)
            line = w
        else:
            line = probe
    out.append(line)
    return out or [""]


def pick_color(current=DEFAULT_COLOR, title=None):
    names = [p[0] for p in PALETTE]
    idx = names.index(current) if current in names else 0
    while True:
        swatches = []
        for i, name in enumerate(names):
            glyph = color_code(name) + term.glyph("●", "*") + term.c("r")
            swatches.append(("[" + glyph + "]") if i == idx else (" " + glyph + " "))
        big = color_code(names[idx])
        body = ["  " + "".join(swatches), "",
                "  " + big + " /\\_/\\ " + term.c("r"),
                "  " + big + "( o.o )" + term.c("r"),
                "  " + big + " > ^ < " + term.c("r")]
        frame(title or t("inst.color"), "", body,
              hints((term.glyph("←→", "<>"), t("ui.move")), ("Enter", t("ok")),
                    ("Esc", t("cancel"))))
        k = term.getkey()
        alt = term.latin(k)
        if k == "left" or alt == "h":
            idx = (idx - 1) % len(names)
        elif k == "right" or alt == "l":
            idx = (idx + 1) % len(names)
        elif k == "enter":
            return names[idx]
        elif k == "esc" or alt == "q":
            return None


def step(msg):
    term.out(term.fit(color_code(DEFAULT_COLOR) + term.glyph("▸ ", "> ") + term.c("r") + msg,
                      term.size()[0] - 1))
    term.flush()
