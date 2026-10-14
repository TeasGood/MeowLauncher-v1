import json
import os
import re
import shutil
import time

from . import loaders, paths, term, ui

FILE = "instance.json"

TEMPLATE = {
    "name": "",
    "color": ui.DEFAULT_COLOR,
    "mc": "",
    "loader": loaders.VANILLA,
    "loader_version": "",
    "version_id": "",
    "ram_mb": None,
    "java_path": "",
    "jvm_args": "",
    "game_args": "",
    "width": 0,
    "height": 0,
    "fullscreen": False,
    "account_id": "",
    "server": "",
    "pre_cmd": "",
    "post_cmd": "",
    "created": 0,
    "last_played": 0,
    "play_count": 0,
}


def slugify(name):
    slug = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip().replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")
    return (slug or "instance")[:48]


def unique_slug(name):
    base = slugify(name)
    slug, n = base, 2
    while os.path.exists(os.path.join(paths.INSTANCES, slug)):
        slug = "%s-%d" % (base, n)
        n += 1
    return slug


def dir_of(inst):
    return os.path.join(paths.INSTANCES, inst["id"])


def game_dir(inst):
    return os.path.join(dir_of(inst), "minecraft")


def mods_dir(inst):
    return os.path.join(game_dir(inst), "mods")


def mod_count(inst):
    folder = mods_dir(inst)
    if not os.path.isdir(folder):
        return 0
    return sum(1 for f in os.listdir(folder) if f.endswith(".jar"))


def load(slug):
    path = os.path.join(paths.INSTANCES, slug, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    inst = dict(TEMPLATE)
    inst.update(data)
    inst["id"] = slug
    return inst


def save(inst):
    folder = dir_of(inst)
    os.makedirs(folder, exist_ok=True)
    payload = {k: v for k, v in inst.items() if k != "id"}
    tmp = os.path.join(folder, FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(folder, FILE))
    return inst


def list_all():
    if not os.path.isdir(paths.INSTANCES):
        return []
    out = []
    for slug in os.listdir(paths.INSTANCES):
        inst = load(slug)
        if inst:
            out.append(inst)
    out.sort(key=lambda i: (-(i.get("last_played") or 0), i.get("name", "").lower()))
    return out


def by_name(needle):
    needle_low = needle.lower()
    items = list_all()
    for inst in items:
        if inst["id"].lower() == needle_low or inst["name"].lower() == needle_low:
            return inst
    for inst in items:
        if needle_low in inst["name"].lower() or needle_low in inst["id"].lower():
            return inst
    return None


def name_taken(name, except_id=""):
    low = name.strip().lower()
    return any(i["name"].strip().lower() == low and i["id"] != except_id for i in list_all())


def create(name, mc, loader=loaders.VANILLA, loader_version="", color=ui.DEFAULT_COLOR):
    inst = dict(TEMPLATE)
    inst.update({
        "id": unique_slug(name),
        "name": name.strip(),
        "mc": mc,
        "loader": loader,
        "loader_version": loader_version,
        "version_id": mc if loader == loaders.VANILLA else "",
        "color": color,
        "created": int(time.time()),
    })
    os.makedirs(mods_dir(inst), exist_ok=True)
    return save(inst)


def duplicate(inst, new_name):
    copy = dict(inst)
    copy["id"] = unique_slug(new_name)
    copy["name"] = new_name
    copy["created"] = int(time.time())
    copy["last_played"] = 0
    copy["play_count"] = 0
    os.makedirs(dir_of(copy), exist_ok=True)
    src = game_dir(inst)
    if os.path.isdir(src):
        shutil.copytree(src, game_dir(copy), dirs_exist_ok=True)
    return save(copy)


def rename(inst, new_name):
    inst["name"] = new_name.strip()
    return save(inst)


def delete(inst):
    shutil.rmtree(dir_of(inst), ignore_errors=True)


def mark_played(inst):
    inst["last_played"] = int(time.time())
    inst["play_count"] = int(inst.get("play_count") or 0) + 1
    save(inst)


def summary(inst):
    bits = [inst["mc"]]
    if inst["loader"] != loaders.VANILLA:
        label = loaders.title(inst["loader"])
        if inst.get("loader_version"):
            label += " " + inst["loader_version"]
        bits.append(label)
        count = mod_count(inst)
        if count:
            from .i18n import t
            bits.append(t("home.mods", n=count))
    return term.glyph(" · ", " | ").join(bits)
