import json
import os
import re
import subprocess

from . import java as java_mod
from . import mojang, net, paths, term, ui
from .i18n import t

VANILLA = "vanilla"
FABRIC = "fabric"
QUILT = "quilt"
FORGE = "forge"
NEOFORGE = "neoforge"
ALL = [VANILLA, FABRIC, QUILT, FORGE, NEOFORGE]

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_MAVEN = "https://maven.minecraftforge.net"
FORGE_META = FORGE_MAVEN + "/net/minecraftforge/forge/maven-metadata.xml"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
NEO_MAVEN = "https://maven.neoforged.net/releases"
NEO_META = NEO_MAVEN + "/net/neoforged/neoforge/maven-metadata.xml"
NEO_LEGACY_META = NEO_MAVEN + "/net/neoforged/forge/maven-metadata.xml"


def title(loader):
    return t("loader." + loader)


def subtitle(loader):
    return t("loader." + loader + ".sub")


def _maven_versions(url, cache_name):
    def load(u):
        return re.findall(r"<version>([^<]+)</version>", net.get_text(u))
    return net.cached_json(cache_name, url, ttl=3600, loader=load)


def _fabric_like(base, mc, cache):
    try:
        data = net.cached_json(cache % mc, "%s/versions/loader/%s" % (base, mc), ttl=3600)
    except Exception:
        return []
    out = []
    for item in data:
        loader = item.get("loader") or {}
        if loader.get("version"):
            out.append({"version": loader["version"], "stable": bool(loader.get("stable"))})
    return out


def neoforge_mc(version):
    core = version.split("-")[0].split("+")[0]
    bits = core.split(".")
    if len(bits) >= 4:
        return "%s.%s.%s" % (bits[0], bits[1], bits[2]) if bits[2] != "0" \
            else "%s.%s" % (bits[0], bits[1])
    if len(bits) == 3:
        return "1.%s.%s" % (bits[0], bits[1]) if bits[1] != "0" else "1." + bits[0]
    return core


def versions(loader, mc):
    if loader == VANILLA:
        return []
    if loader == FABRIC:
        return _fabric_like(FABRIC_META, mc, "fabric-%s.json")
    if loader == QUILT:
        return _fabric_like(QUILT_META, mc, "quilt-%s.json")
    if loader == FORGE:
        try:
            raw = _maven_versions(FORGE_META, "forge-maven.json")
        except Exception:
            return []
        promos = _forge_promos()
        out = []
        for full in reversed(raw):
            if not full.startswith(mc + "-"):
                continue
            short = full[len(mc) + 1:]
            tag = ""
            if promos.get(mc + "-recommended") and short.startswith(promos[mc + "-recommended"]):
                tag = "recommended"
            elif promos.get(mc + "-latest") and short.startswith(promos[mc + "-latest"]):
                tag = "latest"
            out.append({"version": short, "full": full, "stable": tag == "recommended",
                        "tag": tag})
        return out
    if loader == NEOFORGE:
        out = []
        try:
            raw = _maven_versions(NEO_META, "neoforge-maven.json")
        except Exception:
            raw = []
        for v in reversed(raw):
            if neoforge_mc(v) == mc:
                out.append({"version": v, "full": v, "legacy": False,
                            "stable": "beta" not in v and "alpha" not in v})
        if mc == "1.20.1":
            try:
                legacy = _maven_versions(NEO_LEGACY_META, "neoforge-legacy.json")
            except Exception:
                legacy = []
            for v in reversed(legacy):
                if v.startswith("1.20.1-"):
                    out.append({"version": v, "full": v, "legacy": True, "stable": True})
        return out
    return []


def _forge_promos():
    try:
        return net.cached_json("forge-promos.json", FORGE_PROMOS, ttl=3600).get("promos", {})
    except Exception:
        return {}


def supported(loader, mc):
    return bool(versions(loader, mc))


def install(loader, mc, version, cfg=None):
    if loader == VANILLA or not version:
        return mc
    if loader == FABRIC:
        return _install_fabric(FABRIC_META, mc, version, "fabric-loader-%s-%s")
    if loader == QUILT:
        return _install_fabric(QUILT_META, mc, version, "quilt-loader-%s-%s")
    if loader in (FORGE, NEOFORGE):
        return _install_with_installer(loader, mc, version, cfg)
    raise RuntimeError("unknown loader: " + loader)


def _install_fabric(base, mc, version, id_fmt):
    vid = id_fmt % (version, mc)
    target = mojang.version_file(vid)
    if os.path.isfile(target):
        return vid
    url = "%s/versions/loader/%s/%s/profile/json" % (base, mc, version)
    data = net.get_json(url)
    data["id"] = vid
    data.setdefault("inheritsFrom", mc)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return vid


def _installer_url(loader, entry):
    full = entry["full"]
    if loader == FORGE:
        return "%s/net/minecraftforge/forge/%s/forge-%s-installer.jar" % (
            FORGE_MAVEN, full, full)
    if entry.get("legacy"):
        return "%s/net/neoforged/forge/%s/forge-%s-installer.jar" % (NEO_MAVEN, full, full)
    return "%s/net/neoforged/neoforge/%s/neoforge-%s-installer.jar" % (NEO_MAVEN, full, full)


def _entry_for(loader, mc, version):
    for item in versions(loader, mc):
        if item["version"] == version:
            return item
    return {"version": version, "full": version if loader == NEOFORGE else mc + "-" + version,
            "legacy": loader == NEOFORGE and mc == "1.20.1"}


def _version_ids():
    if not os.path.isdir(paths.VERSIONS):
        return set()
    return {d for d in os.listdir(paths.VERSIONS)
            if os.path.isfile(os.path.join(paths.VERSIONS, d, d + ".json"))}


def _stub_profiles():
    path = os.path.join(paths.GAME, "launcher_profiles.json")
    if os.path.isfile(path):
        return
    os.makedirs(paths.GAME, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"profiles": {}, "selectedProfile": "", "clientToken": "",
                   "authenticationDatabase": {}, "launcherVersion":
                       {"name": "MeowLauncher", "format": 21, "profilesFormat": 2}}, f)


def _install_with_installer(loader, mc, version, cfg):
    entry = _entry_for(loader, mc, version)
    already = _find_installed(loader, mc, entry)
    if already:
        return already

    ui.step(t("loader.installing", loader=title(loader), ver=version))
    vanilla = mojang.fetch_version_json(mc)
    mojang.ensure_client(mc, vanilla)
    _stub_profiles()

    java_exe = java_mod.ensure(java_mod.major_for(mc, vanilla),
                               (cfg or {}).get("java_path", ""))
    url = _installer_url(loader, entry)
    installer = os.path.join(paths.CACHE, os.path.basename(url))
    net.download_one(url, installer, title(loader))

    before = _version_ids()
    cmd = [java_exe, "-jar", installer, "--installClient", paths.GAME]
    code, tail = _run_installer(cmd)
    new = _version_ids() - before
    if new:
        return sorted(new, key=len)[-1]
    found = _find_installed(loader, mc, entry)
    if found:
        return found
    raise RuntimeError("%s (%s)\n%s" % (t("loader.fail", loader=title(loader)), code, tail))


def _find_installed(loader, mc, entry):
    needle = entry["version"].split("-", 1)[-1] if entry.get("legacy") else entry["version"]
    tag = "neoforge" if loader == NEOFORGE and not entry.get("legacy") else "forge"
    for vid in _version_ids():
        low = vid.lower()
        if tag not in low:
            continue
        if needle not in vid:
            continue
        if tag == "forge" and mc not in vid:
            continue
        return vid
    return None


def _run_installer(cmd):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", bufsize=1)
    except Exception as e:
        raise RuntimeError(str(e))
    tail = []
    width = term.size()[0] - 6
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-12]
        term.write("\r" + term.fit("    " + line, width) + ("\x1b[K" if term.ENABLED else ""))
        term.flush()
    proc.wait()
    term.write("\r" + " " * min(width, 100) + "\r")
    term.flush()
    return proc.returncode, "\n".join(tail[-6:])
