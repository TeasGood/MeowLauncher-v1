import json
import os
import shutil
import urllib.parse

from . import instances, net
from .i18n import t

MODRINTH = "modrinth"
CURSEFORGE = "curseforge"

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
CF_GAME_ID = 432
CF_CLASS_MOD = 6
CF_LOADERS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}


class Project(object):
    __slots__ = ("source", "id", "slug", "name", "author", "summary", "downloads")

    def __init__(self, source, pid, slug, name, author, summary, downloads):
        self.source = source
        self.id = pid
        self.slug = slug
        self.name = name
        self.author = author
        self.summary = summary
        self.downloads = downloads


class Release(object):
    __slots__ = ("source", "name", "filename", "url", "sha1", "size", "deps",
                 "game_versions", "loaders", "channel")

    def __init__(self, source, name, filename, url, sha1=None, size=None, deps=None,
                 game_versions=None, loaders=None, channel="release"):
        self.source = source
        self.name = name
        self.filename = filename
        self.url = url
        self.sha1 = sha1
        self.size = size
        self.deps = deps or []
        self.game_versions = game_versions or []
        self.loaders = loaders or []
        self.channel = channel


def _modrinth_facets(mc, loader):
    facets = [["project_type:mod"]]
    if mc:
        facets.append(["versions:" + mc])
    if loader and loader != "vanilla":
        facets.append(["categories:" + loader])
    return json.dumps(facets)


def modrinth_search(query, mc, loader, limit=40):
    query = (query or "").strip()
    url = "%s/search?%s" % (MODRINTH_API, urllib.parse.urlencode({
        "query": query, "limit": limit,
        "index": "relevance" if query else "downloads",
        "facets": _modrinth_facets(mc, loader)}))
    data = net.get_json(url)
    out = []
    for hit in data.get("hits", []):
        out.append(Project(MODRINTH, hit["project_id"], hit.get("slug", ""),
                           hit.get("title", ""), hit.get("author", ""),
                           hit.get("description", ""), hit.get("downloads", 0)))
    return out


def modrinth_versions(project_id, mc, loader):
    params = {"game_versions": json.dumps([mc])}
    if loader and loader != "vanilla":
        params["loaders"] = json.dumps([loader])
    url = "%s/project/%s/version?%s" % (MODRINTH_API, project_id,
                                        urllib.parse.urlencode(params))
    out = []
    for item in net.get_json(url):
        files = item.get("files") or []
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary:
            continue
        deps = [d["project_id"] for d in item.get("dependencies") or []
                if d.get("dependency_type") == "required" and d.get("project_id")]
        out.append(Release(MODRINTH, item.get("name") or item.get("version_number", ""),
                           primary["filename"], primary["url"],
                           (primary.get("hashes") or {}).get("sha1"),
                           primary.get("size"), deps,
                           item.get("game_versions"), item.get("loaders"),
                           item.get("version_type", "release")))
    return out


def modrinth_project_name(project_id):
    try:
        return net.get_json("%s/project/%s" % (MODRINTH_API, project_id)).get("title", project_id)
    except Exception:
        return project_id


def _cf_headers(key):
    if not key:
        raise RuntimeError(t("mods.cf.nokey"))
    return {"x-api-key": key, "Accept": "application/json"}


def curseforge_search(query, mc, loader, key, limit=40):
    params = {"gameId": CF_GAME_ID, "classId": CF_CLASS_MOD, "searchFilter": query,
              "pageSize": limit, "sortField": 2, "sortOrder": "desc"}
    if mc:
        params["gameVersion"] = mc
    if loader in CF_LOADERS:
        params["modLoaderType"] = CF_LOADERS[loader]
    url = "%s/mods/search?%s" % (CURSEFORGE_API, urllib.parse.urlencode(params))
    data = net.get_json(url, headers=_cf_headers(key))
    out = []
    for item in data.get("data", []):
        authors = item.get("authors") or []
        out.append(Project(CURSEFORGE, str(item["id"]), item.get("slug", ""),
                           item.get("name", ""), authors[0]["name"] if authors else "",
                           item.get("summary", ""), item.get("downloadCount", 0)))
    return out


def curseforge_versions(project_id, mc, loader, key):
    params = {"pageSize": 50}
    if mc:
        params["gameVersion"] = mc
    if loader in CF_LOADERS:
        params["modLoaderType"] = CF_LOADERS[loader]
    url = "%s/mods/%s/files?%s" % (CURSEFORGE_API, project_id, urllib.parse.urlencode(params))
    data = net.get_json(url, headers=_cf_headers(key))
    out = []
    for item in data.get("data", []):
        url_dl = item.get("downloadUrl")
        if not url_dl:
            continue
        sha1 = None
        for h in item.get("hashes") or []:
            if h.get("algo") == 1:
                sha1 = h.get("value")
        deps = [str(d["modId"]) for d in item.get("dependencies") or []
                if d.get("relationType") == 3]
        out.append(Release(CURSEFORGE, item.get("displayName", ""), item.get("fileName", ""),
                           url_dl, sha1, item.get("fileLength"), deps,
                           item.get("gameVersions"), [], "release"))
    return out


def curseforge_project_name(project_id, key):
    try:
        data = net.get_json("%s/mods/%s" % (CURSEFORGE_API, project_id),
                            headers=_cf_headers(key))
        return data.get("data", {}).get("name", project_id)
    except Exception:
        return project_id


def search(source, query, mc, loader, key=""):
    if source == CURSEFORGE:
        return curseforge_search(query, mc, loader, key)
    return modrinth_search(query, mc, loader)


def releases(source, project_id, mc, loader, key=""):
    if source == CURSEFORGE:
        return curseforge_versions(project_id, mc, loader, key)
    return modrinth_versions(project_id, mc, loader)


def best_release(source, project_id, mc, loader, key=""):
    items = releases(source, project_id, mc, loader, key)
    stable = [r for r in items if r.channel == "release"]
    return (stable or items or [None])[0]


def install(inst, release, with_deps=True, key="", seen=None):
    folder = instances.mods_dir(inst)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, release.filename)
    net.download_one(release.url, dest, release.filename, release.sha1, release.size)
    installed = [release.filename]
    if not with_deps:
        return installed
    seen = seen if seen is not None else set()
    for dep in release.deps:
        if dep in seen:
            continue
        seen.add(dep)
        try:
            dep_release = best_release(release.source, dep, inst["mc"], inst["loader"], key)
        except Exception:
            dep_release = None
        if not dep_release or _has_file(folder, dep_release.filename):
            continue
        installed += install(inst, dep_release, True, key, seen)
    return installed


def _has_file(folder, filename):
    base = filename.lower()
    for name in os.listdir(folder):
        if name.lower() in (base, base + ".disabled"):
            return True
    return False


def install_local(inst, path):
    if not path.lower().endswith(".jar"):
        raise RuntimeError(t("mods.file.bad"))
    folder = instances.mods_dir(inst)
    os.makedirs(folder, exist_ok=True)
    shutil.copy2(path, os.path.join(folder, os.path.basename(path)))
    return os.path.basename(path)


def installed(inst):
    folder = instances.mods_dir(inst)
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder), key=str.lower):
        if name.endswith(".jar"):
            out.append((name, True))
        elif name.endswith(".jar.disabled"):
            out.append((name[:-9], False))
    return out


def toggle(inst, filename, enabled):
    folder = instances.mods_dir(inst)
    src = os.path.join(folder, filename + ("" if not enabled else ".disabled"))
    dst = os.path.join(folder, filename + ("" if enabled else ".disabled"))
    if os.path.isfile(src):
        os.replace(src, dst)


def remove(inst, filename):
    folder = instances.mods_dir(inst)
    for candidate in (filename, filename + ".disabled"):
        path = os.path.join(folder, candidate)
        if os.path.isfile(path):
            os.remove(path)
