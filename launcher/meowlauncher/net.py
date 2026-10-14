import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import USER_AGENT
from . import term
from .i18n import t

THREADS = 12
TIMEOUT = 30


class NetError(RuntimeError):
    pass


def set_threads(n):
    global THREADS
    THREADS = max(1, min(32, int(n)))


def _request(url, data=None, headers=None, method=None):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        h.update(headers)
    return urllib.request.Request(url, data=data, headers=h, method=method)


def open_url(url, timeout=TIMEOUT, headers=None):
    try:
        return urllib.request.urlopen(_request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError:
        raise
    except Exception as e:
        raise NetError(t("err.net", host=urllib.parse.urlparse(url).netloc)) from e


def get_bytes(url, timeout=TIMEOUT, headers=None):
    with open_url(url, timeout, headers) as r:
        return r.read()


def get_json(url, timeout=TIMEOUT, headers=None):
    return json.loads(get_bytes(url, timeout, headers).decode("utf-8"))


def get_text(url, timeout=TIMEOUT, headers=None):
    return get_bytes(url, timeout, headers).decode("utf-8", "replace")


def post_json(url, payload, headers=None, timeout=TIMEOUT, form=False):
    if form:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        ct = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(payload).encode("utf-8")
        ct = "application/json"
    h = {"Content-Type": ct}
    if headers:
        h.update(headers)
    req = _request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw or "{}")
        except Exception:
            return e.code, {"raw": raw}
    except Exception as e:
        raise NetError(t("err.net", host=urllib.parse.urlparse(url).netloc)) from e


class Bar:

    def __init__(self, label, total, unit="n"):
        self.label = label
        self.total = max(1, total)
        self.done = 0
        self.unit = unit
        self.lock = threading.Lock()
        self.last = 0.0
        self.closed = False

    def _fmt(self, v):
        if self.unit == "b":
            return "%.1f MB" % (v / 1048576.0)
        return str(int(v))

    def update(self, n=1, force=False):
        with self.lock:
            self.done = max(0, self.done + n)
            now = time.time()
            if not force and now - self.last < 0.08 and self.done < self.total:
                return
            self.last = now
            self._draw()

    def _draw(self):
        cols = term.size()[0]
        tail = " %s / %s" % (self._fmt(self.done), self._fmt(self.total))
        label = term.fit(self.label, max(8, min(18, cols // 4)))
        width = cols - term.wlen(label) - term.wlen(tail) - 6
        width = max(6, min(36, width))
        filled = min(width, int(width * self.done / self.total))
        bar = term.glyph("█", "#") * filled + term.glyph("░", ".") * (width - filled)
        line = "  %s [%s]%s" % (label, bar, tail)
        clear_eol = "\x1b[K" if term.ENABLED else ""
        term.write("\r" + term.fit(line, cols - 1) + clear_eol)
        term.flush()

    def close(self):
        if self.closed:
            return
        self.closed = True
        with self.lock:
            self.done = self.total
            self._draw()
        term.write("\n")
        term.flush()


def download(url, dest, sha1=None, retries=3, bar=None, headers=None):
    from .paths import fs
    os.makedirs(fs(os.path.dirname(dest) or "."), exist_ok=True)
    last = None
    for attempt in range(retries):
        tmp = fs(dest + ".part")
        h = hashlib.sha1()
        got = 0
        try:
            with open_url(url, 90, headers) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(131072)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if bar and bar.unit == "b":
                        bar.update(len(chunk))
            if sha1 and h.hexdigest() != sha1:
                raise NetError("sha1 mismatch: " + os.path.basename(dest))
            os.replace(tmp, fs(dest))
            return dest
        except Exception as e:
            last = e
            if bar and bar.unit == "b" and got:
                bar.update(-got, force=True)
            try:
                os.remove(tmp)
            except OSError:
                pass
            time.sleep(0.7 * (attempt + 1))
    raise NetError("%s: %s" % (url, last))


def download_many(tasks, label):
    from .paths import fs
    todo = []
    for url, dest, sha1, size in tasks:
        probe = fs(dest)
        if os.path.isfile(probe):
            if size and os.path.getsize(probe) == size:
                continue
            if not size and os.path.getsize(probe) > 0:
                continue
        todo.append((url, dest, sha1))
    if not todo:
        return 0
    bar = Bar(label, len(todo))
    errors = []
    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        futures = {ex.submit(download, u, d, s): d for u, d, s in todo}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                errors.append(e)
            bar.update(1)
    bar.close()
    if errors:
        raise errors[0]
    return len(todo)


def download_one(url, dest, label, sha1=None, size=None):
    if os.path.isfile(dest) and (not size or os.path.getsize(dest) == size):
        return dest
    bar = Bar(label, size or 1, unit="b" if size else "n")
    try:
        download(url, dest, sha1, bar=bar if size else None)
    finally:
        bar.close()
    return dest


def cached_json(name, url, ttl=3600, headers=None, loader=None):
    from .paths import CACHE
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.isfile(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        data = loader(url) if loader else get_json(url, headers=headers)
    except Exception:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        raise
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data
