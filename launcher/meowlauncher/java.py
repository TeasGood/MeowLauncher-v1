import os
import platform
import re
import shutil
import subprocess
import tarfile
import zipfile

from . import net, paths, ui
from .i18n import t

ADOPTIUM_ASSETS = ("https://api.adoptium.net/v3/assets/latest/%s/hotspot"
                   "?os=%s&architecture=%s&image_type=jre&vendor=eclipse")
ADOPTIUM_BINARY = ("https://api.adoptium.net/v3/binary/latest/%s/ga/%s/%s/jre/"
                   "hotspot/normal/eclipse")


def arch():
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "aarch64"
    if m in ("i386", "i686", "x86"):
        return "x86"
    if m.startswith("arm"):
        return "arm"
    return "x64"


def _os_name():
    return "windows" if paths.IS_WIN else ("mac" if paths.IS_MAC else "linux")


def major_for(mc_id, version_json=None):
    if version_json:
        jv = version_json.get("javaVersion") or {}
        if jv.get("majorVersion"):
            return int(jv["majorVersion"])
    parts = re.findall(r"\d+", mc_id or "")
    if not parts:
        return 21
    first = int(parts[0])
    if first >= 25:
        return 25
    if first != 1:
        return 21
    minor = int(parts[1]) if len(parts) > 1 else 0
    if minor <= 16:
        return 8
    if minor < 20:
        return 17
    if minor == 20:
        patch = int(parts[2]) if len(parts) > 2 else 0
        return 17 if patch < 5 else 21
    return 21


def _exe_in(folder):
    name = "java.exe" if paths.IS_WIN else "java"
    if not os.path.isdir(folder):
        return None
    for root, _dirs, files in os.walk(folder):
        if name in files and os.path.basename(root) == "bin":
            return os.path.join(root, name)
    return None


def version_of(exe):
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=25)
    except Exception:
        return None
    text = (r.stderr or "") + (r.stdout or "")
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        return None
    first = int(m.group(1))
    return int(m.group(2) or 0) if first == 1 else first


def find_installed(major):
    exe = _exe_in(paths.P("runtime", "java%d" % major))
    if exe and os.path.isfile(exe):
        return exe
    for name in ("java",):
        found = shutil.which(name)
        if found and version_of(found) == major:
            return found
    env = os.environ.get("JAVA_HOME")
    if env:
        exe = _exe_in(env)
        if exe and version_of(exe) == major:
            return exe
    return None


def _download_info(major):
    url = ADOPTIUM_ASSETS % (major, _os_name(), arch())
    try:
        data = net.get_json(url)
        binary = data[0]["binary"]["package"]
        return binary["link"], binary.get("size"), binary.get("checksum")
    except Exception:
        return ADOPTIUM_BINARY % (major, _os_name(), arch()), None, None


def install(major):
    link, size, sha256 = _download_info(major)
    ui.step(t("run.java", ver=major))
    dest = paths.P("runtime", "java%d" % major)
    suffix = ".zip" if link.endswith(".zip") else ".tar.gz"
    archive = paths.P("runtime", "java%d%s" % (major, suffix))
    os.makedirs(paths.RUNTIME, exist_ok=True)
    net.download_one(link, archive, "Java %d" % major, size=size)
    if sha256:
        import hashlib
        h = hashlib.sha256()
        with open(archive, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha256:
            os.remove(archive)
            raise net.NetError("Java: checksum mismatch")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as tar:
            try:
                tar.extractall(dest, filter="data")
            except TypeError:
                tar.extractall(dest)
    os.remove(archive)
    exe = _exe_in(dest)
    if not exe:
        raise RuntimeError(t("err.java"))
    if not paths.IS_WIN:
        for root, _d, files in os.walk(dest):
            if os.path.basename(root) == "bin":
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o755)
                    except OSError:
                        pass
    if version_of(exe) is None:
        raise RuntimeError(t("err.java"))
    return exe


def ensure(major, override=""):
    if override:
        override = os.path.expanduser(override)
        if os.path.isdir(override):
            found = _exe_in(override)
            if found:
                return found
        if os.path.isfile(override):
            return override
    exe = find_installed(major)
    if exe:
        return exe
    return install(major)
