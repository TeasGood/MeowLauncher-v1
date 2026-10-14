import json
import os
import platform
import re
import shutil
import zipfile

from . import net, paths
from .i18n import t

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES = "https://resources.download.minecraft.net/"
MIN_VERSION = "1.8.9"


def manifest(ttl=1800):
    return net.cached_json("manifest.json", MANIFEST, ttl=ttl)


def version_list(snapshots=False, old=False):
    out = []
    for v in manifest()["versions"]:
        kind = v["type"]
        if kind == "release" or (kind == "snapshot" and snapshots) or \
                (kind not in ("release", "snapshot") and old):
            out.append({"id": v["id"], "type": kind, "url": v["url"],
                        "date": (v.get("releaseTime") or "")[:10]})
        if v["id"] == MIN_VERSION and not old:
            break
    return out


def latest_release():
    return manifest()["latest"]["release"]


def version_dir(vid):
    return os.path.join(paths.VERSIONS, vid)


def version_file(vid):
    return os.path.join(version_dir(vid), vid + ".json")


def local_version_json(vid):
    path = version_file(vid)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def fetch_version_json(vid):
    data = local_version_json(vid)
    if data:
        return data
    entry = None
    for v in manifest()["versions"]:
        if v["id"] == vid:
            entry = v
            break
    if not entry:
        raise RuntimeError(t("loader.none", mc=vid))
    data = net.get_json(entry["url"])
    os.makedirs(version_dir(vid), exist_ok=True)
    with open(version_file(vid), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def resolve(vid):
    chain, seen = [], set()
    cur = vid
    while cur and cur not in seen:
        seen.add(cur)
        data = local_version_json(cur) or fetch_version_json(cur)
        chain.append(data)
        cur = data.get("inheritsFrom")
    merged = {}
    for data in reversed(chain):
        merged = _merge(merged, data)
    merged.setdefault("jar", chain[-1].get("id", vid))
    merged["id"] = vid
    return merged


def _merge(parent, child):
    out = dict(parent)
    for key, value in child.items():
        if key == "libraries":
            out["libraries"] = list(value) + list(parent.get("libraries", []))
        elif key == "arguments":
            args = dict(parent.get("arguments", {}))
            for side in ("jvm", "game"):
                if side in value:
                    args[side] = list(args.get(side, [])) + list(value[side])
            out["arguments"] = args
        elif key == "inheritsFrom":
            continue
        else:
            out[key] = value
    if "minecraftArguments" in child and "arguments" in parent:
        out.pop("arguments", None)
    return out


def rules_ok(rules, features=None):
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        match = True
        for feat, want in (rule.get("features") or {}).items():
            if bool(features.get(feat)) != bool(want):
                match = False
        osr = rule.get("os") or {}
        if "name" in osr and osr["name"] != paths.OS_NAME:
            match = False
        if "arch" in osr and (osr["arch"] == "x86") == paths.IS_64:
            match = False
        if "version" in osr:
            try:
                if not re.search(osr["version"], platform.version()):
                    match = False
            except re.error:
                pass
        if match:
            allowed = rule.get("action") == "allow"
    return allowed


def maven_parts(name):
    ext = "jar"
    if "@" in name:
        name, ext = name.rsplit("@", 1)
    bits = name.split(":")
    group, artifact, version = bits[0], bits[1], bits[2]
    classifier = bits[3] if len(bits) > 3 else ""
    filename = "%s-%s%s.%s" % (artifact, version, "-" + classifier if classifier else "", ext)
    return group.split("."), artifact, version, filename


def maven_path(name):
    groups, artifact, version, filename = maven_parts(name)
    return os.path.join(paths.LIBRARIES, *(groups + [artifact, version, filename]))


def maven_url(base, name):
    groups, artifact, version, filename = maven_parts(name)
    return base.rstrip("/") + "/" + "/".join(groups + [artifact, version, filename])


def _native_key(lib):
    natives = lib.get("natives") or {}
    key = natives.get(paths.OS_NAME)
    if not key:
        return None
    return key.replace("${arch}", "64" if paths.IS_64 else "32")


def libraries(vj, features=None):
    classpath, natives, tasks, seen = [], [], [], set()
    for lib in vj.get("libraries", []):
        if not rules_ok(lib.get("rules"), features):
            continue
        name = lib.get("name", "")
        downloads = lib.get("downloads") or {}
        artifact = downloads.get("artifact")
        native_key = _native_key(lib)
        if artifact and not native_key:
            path = os.path.join(paths.LIBRARIES, *artifact["path"].split("/"))
            url = artifact.get("url") or ""
            if url:
                tasks.append((url, path, artifact.get("sha1"), artifact.get("size")))
            if path not in seen:
                seen.add(path)
                classpath.append(path)
            if ":natives-" in name:
                natives.append(path)
        elif native_key:
            classifier = (downloads.get("classifiers") or {}).get(native_key)
            if classifier:
                path = os.path.join(paths.LIBRARIES, *classifier["path"].split("/"))
                tasks.append((classifier["url"], path, classifier.get("sha1"),
                              classifier.get("size")))
                natives.append(path)
            elif name:
                path = maven_path(name + ":" + native_key)
                base = lib.get("url") or "https://libraries.minecraft.net/"
                tasks.append((maven_url(base, name + ":" + native_key), path, None, None))
                natives.append(path)
        elif name:
            path = maven_path(name)
            base = lib.get("url") or "https://libraries.minecraft.net/"
            if not os.path.isfile(paths.fs(path)):
                tasks.append((maven_url(base, name), path, None, None))
            if path not in seen:
                seen.add(path)
                classpath.append(path)
    return classpath, natives, tasks


def extract_natives(jars, outdir):
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)
    for jar in jars:
        jar = paths.fs(jar)
        if not os.path.isfile(jar):
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                for entry in z.namelist():
                    base = os.path.basename(entry)
                    if entry.endswith("/") or entry.startswith("META-INF/") or not base:
                        continue
                    if not base.lower().endswith((".dll", ".so", ".dylib", ".jnilib")):
                        continue
                    with z.open(entry) as src, open(os.path.join(outdir, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile:
            continue


def ensure_assets(vj):
    index = vj.get("assetIndex")
    if not index:
        return
    index_path = os.path.join(paths.ASSETS, "indexes", index["id"] + ".json")
    if not os.path.isfile(index_path):
        net.download(index["url"], index_path, index.get("sha1"))
    with open(index_path, encoding="utf-8") as f:
        data = json.load(f)
    objects = data.get("objects", {})
    tasks, seen = [], set()
    for obj in objects.values():
        h = obj["hash"]
        if h in seen:
            continue
        seen.add(h)
        tasks.append((RESOURCES + h[:2] + "/" + h,
                      os.path.join(paths.ASSETS, "objects", h[:2], h), h, obj.get("size")))
    net.download_many(tasks, t("run.assets"))
    if data.get("virtual") or data.get("map_to_resources"):
        _materialize(objects, index["id"], data.get("map_to_resources", False))


def _materialize(objects, index_id, to_resources):
    root = os.path.join(paths.ASSETS, "virtual", "legacy" if not to_resources else index_id)
    for name, obj in objects.items():
        h = obj["hash"]
        src = os.path.join(paths.ASSETS, "objects", h[:2], h)
        dst = os.path.join(root, *name.split("/"))
        if os.path.isfile(dst) or not os.path.isfile(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def ensure_client(vid, vj):
    downloads = vj.get("downloads") or {}
    client = downloads.get("client")
    base_id = vj.get("jar") or vid
    base_path = os.path.join(version_dir(base_id), base_id + ".jar")
    if client:
        net.download_many([(client["url"], base_path, client.get("sha1"),
                            client.get("size"))], t("run.client"))
    if base_id == vid:
        return base_path
    path = os.path.join(version_dir(vid), vid + ".jar")
    if not os.path.isfile(paths.fs(path)) and os.path.isfile(paths.fs(base_path)):
        os.makedirs(version_dir(vid), exist_ok=True)
        shutil.copyfile(paths.fs(base_path), paths.fs(path))
    return path


def _collect(args, features):
    out = []
    for arg in args:
        if isinstance(arg, str):
            out.append(arg)
        elif rules_ok(arg.get("rules"), features):
            value = arg.get("value")
            out.extend([value] if isinstance(value, str) else list(value))
    return out


def substitute(value, ctx):
    return re.sub(r"\$\{([^}]+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), value)


def build_args(vj, ctx, features=None):
    features = features or {}
    if "arguments" in vj:
        jvm = _collect(vj["arguments"].get("jvm", []), features)
        game = _collect(vj["arguments"].get("game", []), features)
    else:
        jvm = ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]
        game = (vj.get("minecraftArguments") or "").split()
        if features.get("has_custom_resolution"):
            game += ["--width", "${resolution_width}", "--height", "${resolution_height}"]
    if not any(a.startswith("-cp") or a == "-cp" for a in jvm):
        jvm += ["-cp", "${classpath}"]
    jvm = [substitute(a, ctx) for a in jvm]
    game = [substitute(a, ctx) for a in game]
    return jvm, vj["mainClass"], game
