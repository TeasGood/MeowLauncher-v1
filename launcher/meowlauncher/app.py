import os
import sys
import time

from . import APP, VERSION
from . import auth, config, desktop, i18n, instances, launch, loaders
from . import mods as mods_api
from . import mojang, net, paths, qr, term, ui
from .i18n import t

HELP = """{app} {ver} - TUI-лаунчер Minecraft

  python MeowLauncher.py [options]
  meow [options]              (after install.sh / install.ps1)

  -p, --play [NAME]   launch an instance right away (default: the last one)
  -l, --list          list instances and exit
      --lang CODE     interface language for this run (e.g. ru, en, zh-Hans)
      --nocolor       no colours and no escape codes
      --ascii         ASCII only, no box-drawing characters
      --threads N     parallel downloads (default 12)
      --home DIR      data folder (same as MEOW_HOME)
  -V, --version       print version
  -h, --help          this help

Environment: MEOW_HOME, MEOW_LANG, MEOW_MS_CLIENT_ID, MEOW_CF_KEY, NO_COLOR
"""


class App(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.store = config.load_accounts()
        self.sessions = {}

    def session(self, inst_id):
        running = self.sessions.get(inst_id)
        if running and running.alive():
            return running
        self.sessions.pop(inst_id, None)
        return None

    @property
    def accounts(self):
        return self.store["accounts"]

    def active_account(self):
        for acc in self.accounts:
            if acc["id"] == self.store.get("active"):
                return acc
        return self.accounts[0] if self.accounts else None

    def save_accounts(self):
        config.save_accounts(self.store)

    def header_sub(self):
        acc = self.active_account()
        if not acc:
            return t("acc.none")
        kind = t("acc.microsoft") if acc["type"] == auth.MICROSOFT else t("acc.offline")
        line = "%s %s %s" % (acc["name"], term.glyph("·", "|"), kind)
        if auth.is_expired(acc):
            line += " (%s)" % t("accs.expired")
        return line

    def run(self):
        if self.cfg.get("lang") is None:
            picked = self.choose_language(first_run=True)
            self.cfg["lang"] = picked or i18n.system_lang()
            self.cfg.save()
            i18n.set_lang(self.cfg["lang"])
        self.home()

    def choose_language(self, first_run=False):
        guess = i18n.system_lang()
        rows, codes = [], []
        for code, native, english in i18n.languages():
            badge = ""
            if code == guess:
                badge = ui.dim("(" + t("lang.sys") + ")")
            sub = english if english.lower() != native.lower() else ""
            rows.append(ui.Row(native, sub=sub, badge=badge))
            codes.append(code)
        if guess in codes:
            i = codes.index(guess)
            rows.insert(0, rows.pop(i))
            codes.insert(0, codes.pop(i))
        sel = codes.index(self.cfg.get("lang")) if self.cfg.get("lang") in codes else 0
        action, idx, key = ui.select(t("lang.title"), rows, sel=sel, sub=t("lang.sub"),
                                search="always")
        if action != "pick":
            return None
        i18n.set_lang(codes[idx])
        return codes[idx]

    def home(self):
        sel = 0
        while True:
            items = instances.list_all()
            rows = []
            for i in items:
                badge = ""
                if self.session(i["id"]):
                    badge = ui.color_code("lime") + term.glyph("▶", ">") + term.c("r")
                rows.append(ui.Row(i["name"], sub=instances.summary(i),
                                   color=i.get("color"), badge=badge))
            rows.append(ui.Row(term.glyph("＋ ", "+ ") + t("home.new"), color=None))
            keys = {"n": t("home.key.new"), "e": t("home.key.menu"),
                    "a": t("home.key.acc"), "s": t("home.key.set")}
            action, idx, key = ui.select(t("home.title"), rows, sel=min(sel, len(rows) - 1),
                                         sub=self.header_sub(), search="slash", keys=keys,
                                         empty=t("home.empty"),
                                         pick_label=t("inst.play").lower())
            if action == "back":
                return
            if action == "key":
                sel = max(0, idx)
                if key == "n":
                    self.new_instance()
                elif key == "a":
                    self.accounts_screen()
                elif key == "s":
                    self.settings_screen()
                elif key == "e" and 0 <= idx < len(items):
                    self.instance_menu(items[idx])
                continue
            sel = idx
            if idx >= len(items):
                self.new_instance()
            else:
                self.play(items[idx])

    def new_instance(self):
        name = ui.ask(t("new.name"), sub=t("new.title"), hint=t("inst.name"))
        if name is None:
            return
        name = name.strip()
        if not name:
            ui.error(t("inst.name.bad"))
            return
        if instances.name_taken(name):
            ui.error(t("inst.exists"))
            return
        mc = self.pick_version(title=t("new.version"))
        if not mc:
            return
        loader = self.pick_loader(mc, title=t("new.loader"))
        if loader is None:
            return
        loader_version = ""
        if loader != loaders.VANILLA:
            loader_version = self.pick_loader_version(loader, mc)
            if not loader_version:
                return
        color = ui.pick_color(ui.DEFAULT_COLOR, title=t("new.color"))
        if color is None:
            return
        inst = instances.create(name, mc, loader, loader_version, color)
        ui.message(t("new.title"), t("new.created", name=inst["name"]), kind="ok")

    def pick_version(self, title=None, current=""):
        try:
            ui.frame(title or t("ver.title"), "", ["  " + ui.dim(t("ver.loading"))])
            show_snapshots = bool(self.cfg.get("show_snapshots"))
            listing = mojang.version_list(snapshots=show_snapshots)
        except Exception as e:
            ui.error(str(e))
            return None
        while True:
            rows, ids = [], []
            latest = mojang.manifest()["latest"]["release"]
            for item in listing:
                badge = ""
                if item["id"] == latest:
                    badge = ui.dim("(" + t("ver.latest") + ")")
                kind = t("ver." + ("snapshot" if item["type"] == "snapshot" else "release"))
                rows.append(ui.Row(item["id"], sub="%s %s %s" % (kind, term.glyph("·", "|"),
                                                                 item["date"]), badge=badge))
                ids.append(item["id"])
            sel = ids.index(current) if current in ids else 0
            action, idx, key = ui.select(title or t("ver.title"), rows, sel=sel,
                                         search="always")
            if action == "back":
                return None
            if action == "pick":
                return ids[idx]

    def pick_loader(self, mc, title=None, current=None):
        rows, keys = [], []
        for loader in loaders.ALL:
            rows.append(ui.Row(loaders.title(loader), sub=loaders.subtitle(loader)))
            keys.append(loader)
        sel = keys.index(current) if current in keys else 0
        action, idx, key = ui.select(title or t("loader.title"), rows, sel=sel)
        if action != "pick":
            return None
        return keys[idx]

    def pick_loader_version(self, loader, mc):
        try:
            ui.frame(t("new.loaderver", loader=loaders.title(loader)), "",
                     ["  " + ui.dim(t("loading"))])
            listing = loaders.versions(loader, mc)
        except Exception as e:
            ui.error(str(e))
            return None
        if not listing:
            ui.error(t("loader.none", mc=mc))
            return None
        rows = []
        for item in listing:
            tag = item.get("tag") or ("" if item.get("stable", True) else "beta")
            sub = {"recommended": t("loader.latest"), "latest": t("ver.latest")}.get(tag, tag)
            rows.append(ui.Row(item["version"], sub=sub))
        action, idx, key = ui.select(t("new.loaderver", loader=loaders.title(loader)), rows,
                                search="always", sub="Minecraft " + mc)
        if action != "pick":
            return None
        return listing[idx]["version"]

    def instance_menu(self, inst):
        while True:
            running = self.session(inst["id"])
            rows = [
                ui.Row(t("inst.play") if not running else t("inst.stop"),
                       badge="" if not running
                       else ui.color_code("lime") + term.glyph("▶", ">") + term.c("r")),
                ui.Row(t("inst.mods"), sub=t("mods.count", n=instances.mod_count(inst))),
                ui.Row(t("inst.settings")),
                ui.Row(t("inst.folder")),
                ui.Row(t("inst.rename")),
                ui.Row(t("inst.color")),
                ui.Row(t("inst.copy")),
                ui.Row(t("inst.delete"), dimmed=True),
            ]
            action, idx, key = ui.select(inst["name"], rows, sub=instances.summary(inst))
            if action != "pick":
                return
            if idx == 0:
                if running:
                    if ui.confirm(t("inst.stop.ask", name=inst["name"])):
                        running.stop()
                        self.sessions.pop(inst["id"], None)
                else:
                    self.play(inst)
            elif idx == 1:
                self.mods_screen(inst)
            elif idx == 2:
                self.instance_settings(inst)
            elif idx == 3:
                self.open_folder(instances.game_dir(inst))
            elif idx == 4:
                name = ui.ask(t("inst.rename"), inst["name"])
                if name and name.strip() and not instances.name_taken(name, inst["id"]):
                    instances.rename(inst, name)
                elif name is not None:
                    ui.error(t("inst.exists"))
            elif idx == 5:
                color = ui.pick_color(inst.get("color", ui.DEFAULT_COLOR))
                if color:
                    inst["color"] = color
                    instances.save(inst)
            elif idx == 6:
                name = ui.ask(t("inst.copy"), inst["name"] + " 2")
                if name and name.strip() and not instances.name_taken(name):
                    instances.duplicate(inst, name.strip())
                    ui.toast(t("inst.copied"))
                    time.sleep(0.6)
            elif idx == 7:
                if ui.confirm(t("inst.delete.ask", name=inst["name"])):
                    instances.delete(inst)
                    return

    def open_folder(self, path):
        if not desktop.open_folder(path):
            ui.message(t("inst.folder"), t("inst.folder.fail") + "\n" + path)

    def mods_screen(self, inst):
        if inst["loader"] == loaders.VANILLA:
            ui.message(t("inst.mods"), t("mods.vanilla"))
            return
        sel = 0
        while True:
            listing = mods_api.installed(inst)
            sources = [mods_api.MODRINTH]
            rows = [ui.Row(t("mods.browse"))]
            if config.SHOW_CURSEFORGE:
                sources.append(mods_api.CURSEFORGE)
                rows.append(ui.Row(t("mods.browse.cf")))
            rows += [ui.Row(t("mods.file")), ui.Row(t("mods.folder"))]
            head = len(rows)
            for name, enabled in listing:
                rows.append(ui.Row(name, sub="" if enabled else t("mods.off"),
                                   dimmed=not enabled))
            action, idx, key = ui.select(
                t("mods.title", name=inst["name"]), rows, sel=min(sel, len(rows) - 1),
                sub=instances.summary(inst), search="slash",
                keys={"x": t("mods.toggle"), "d": t("delete")},
                empty=t("mods.empty"))
            if action == "back":
                return
            if action == "key":
                sel = max(0, idx)
                pos = idx - head
                if 0 <= pos < len(listing):
                    name, enabled = listing[pos]
                    if key == "x":
                        mods_api.toggle(inst, name, not enabled)
                    elif key == "d" and ui.confirm(t("mods.delete.ask", name=name)):
                        mods_api.remove(inst, name)
                continue
            sel = idx
            if idx < len(sources):
                source = sources[idx]
                if source == mods_api.CURSEFORGE and not self.cfg.get("cf_key"):
                    ui.message(t("mods.browse.cf"), t("mods.cf.nokey"))
                else:
                    self.mod_browser(inst, source)
            elif idx == len(sources):
                path = ui.ask(t("mods.file"), hint=t("mods.file.ask"))
                if path:
                    try:
                        name = mods_api.install_local(inst, os.path.expanduser(path.strip()))
                        ui.toast(t("mods.installed", name=name))
                        time.sleep(0.6)
                    except Exception as e:
                        ui.error(str(e))
            else:
                self.open_folder(instances.mods_dir(inst))

    def mod_browser(self, inst, source):
        title = t("mods.browse.cf") if source == mods_api.CURSEFORGE else t("mods.browse")
        state = {"found": [], "rows": [], "note": "", "query": ""}

        def fetch(query):
            try:
                found = mods_api.search(source, query, inst["mc"], inst["loader"],
                                        self.cfg.get("cf_key", ""))
                note = "" if query.strip() else t("mods.popular")
            except Exception:
                found, note = [], t("mods.offline")
            rows = []
            for project in found:
                sub = project.author
                if project.downloads:
                    sub += "  " + t("mods.downloads", n=_short_number(project.downloads))
                rows.append(ui.Row(project.name, sub=sub))
            state.update(found=found, rows=rows, note=note, query=query)
            return rows, note

        ui.frame(title, instances.summary(inst), ["  " + ui.dim(t("mods.searching"))])
        fetch("")
        while True:
            action, idx, key = ui.select(
                title, state["rows"], sub=instances.summary(inst), search="always",
                query=state["query"], fetch=fetch, busy=t("mods.searching"),
                note=state["note"], empty=t("mods.noresults"))
            if action != "pick" or idx >= len(state["found"]):
                return
            self.install_mod(inst, state["found"][idx], source)

    def install_mod(self, inst, project, source):
        try:
            ui.frame(project.name, inst["name"], ["  " + ui.dim(t("loading"))])
            found = mods_api.releases(source, project.id, inst["mc"], inst["loader"],
                                      self.cfg.get("cf_key", ""))
        except Exception:
            ui.error(t("mods.offline"))
            return
        if not found:
            ui.message(project.name, t("mods.nover", mc=inst["mc"],
                                       loader=loaders.title(inst["loader"])))
            return
        rows = [ui.Row(r.name or r.filename, sub=r.filename) for r in found]
        action, idx, key = ui.select(t("mods.pickver"), rows, sub=project.name)
        if action != "pick":
            return
        release = found[idx]
        ui.frame(project.name, inst["name"],
                 ["  " + t("mods.installing", name=release.filename), ""])
        try:
            added = mods_api.install(inst, release, True, self.cfg.get("cf_key", ""))
        except Exception as e:
            ui.error(str(e))
            return
        extra = added[1:]
        text = t("mods.installed", name=release.filename)
        if extra:
            text += "\n" + t("mods.deps", list=", ".join(extra))
        ui.message(project.name, text, kind="ok")

    def accounts_screen(self):
        sel = 0
        while True:
            adders = []
            rows = []
            if config.SHOW_MICROSOFT:
                adders.append(self.add_microsoft)
                rows.append(ui.Row(t("accs.add.ms")))
            adders.append(self.add_offline)
            rows.append(ui.Row(t("accs.add.offline")))
            head = len(adders)
            for acc in self.accounts:
                kind = t("acc.microsoft") if acc["type"] == auth.MICROSOFT else t("acc.offline")
                badge = ""
                if acc["id"] == self.store.get("active"):
                    badge = ui.color_code("lime") + term.glyph("✓", "*") + term.c("r")
                sub = kind
                if auth.is_expired(acc):
                    sub += " " + term.glyph("·", "|") + " " + t("accs.expired")
                rows.append(ui.Row(acc["name"], sub=sub, badge=badge))
            action, idx, key = ui.select(t("accs.title"), rows, sel=min(sel, len(rows) - 1),
                                    sub=self.header_sub(), keys={"d": t("accs.remove")},
                                    empty=t("accs.empty"))
            if action == "back":
                return
            if action == "key" and key == "d":
                sel = max(0, idx)
                pos = idx - head
                if 0 <= pos < len(self.accounts):
                    acc = self.accounts[pos]
                    if ui.confirm(t("accs.remove.ask", name=acc["name"])):
                        self.accounts.remove(acc)
                        if self.store.get("active") == acc["id"]:
                            self.store["active"] = self.accounts[0]["id"] if self.accounts else ""
                        self.save_accounts()
                continue
            sel = idx
            if idx < head:
                adders[idx]()
            else:
                acc = self.accounts[idx - head]
                self.store["active"] = acc["id"]
                self.save_accounts()

    def add_offline(self):
        nick = ui.ask(t("accs.add.offline"), hint=t("accs.nick.bad"),
                      allowed=lambda ch: ch.isascii() and (ch.isalnum() or ch == "_"),
                      maxlen=16)
        if not nick:
            return
        if not auth.valid_nick(nick):
            ui.error(t("accs.nick.bad"))
            return
        account = auth.make_offline(nick)
        self._store_account(account)

    def _store_account(self, account):
        self.store["accounts"] = [a for a in self.accounts if a["id"] != account["id"]]
        self.store["accounts"].append(account)
        self.store["active"] = account["id"]
        self.save_accounts()

    def add_microsoft(self):
        client_id = self.cfg.get("ms_client_id", "")
        if not client_id:
            ui.message(t("accs.ms.title"), t("accs.ms.noid") + "\n\n" + t("set.msid.help"))
            entered = ui.ask(t("accs.ms.idask"), hint=t("set.msid.help"))
            if not entered:
                return
            client_id = entered.strip()
            self.cfg["ms_client_id"] = client_id
            self.cfg.save()

        def on_code(url, code, link):
            opened = desktop.open_url(link)
            copied = desktop.copy_to_clipboard(code)
            self._draw_device_code(url, code, link, opened, copied)

        def cancelled():
            if term.kbhit():
                return term.getkey() == "esc"
            return False

        try:
            account = auth.login_microsoft(client_id, on_code, cancelled)
        except auth.Cancelled:
            return
        except Exception as e:
            ui.error(str(e), sub=t("accs.ms.title"))
            return
        self._store_account(account)
        ui.message(t("accs.ms.title"), t("accs.ms.ok", name=account["name"]), kind="ok")

    def _draw_device_code(self, url, code, link, opened=False, copied=False):
        cols, rows = term.size()
        big = ui.color_code("lime") + term.c("b") + code + term.c("r")
        info = [term.c("b") + t("accs.ms.scan") + term.c("r"), "",
                t("accs.ms.manual"), "  " + url, t("accs.ms.enter"), "  " + big, ""]
        if copied:
            info.append(ui.dim(t("accs.ms.copied")))
        info.append(ui.dim(t("accs.ms.waiting")))

        picture = self._qr_lines(link, cols, rows, info)
        if picture:
            width = term.wlen(picture[0])
            top = max(0, (len(picture) - len(info)) // 2)
            body = []
            for i in range(max(len(picture), top + len(info))):
                left = picture[i] if i < len(picture) else " " * width
                j = i - top
                right = info[j] if 0 <= j < len(info) else ""
                body.append(" " + left + "   " + right)
        else:
            body = [""] + ["  " + line for line in info]
        if not opened:
            body.append("")
        ui.frame(t("accs.ms.title"), "", body, t("accs.ms.cancel"))

    FRAME_ROWS = 7

    @staticmethod
    def _qr_lines(link, cols, rows, info):
        if not link or not term.ENABLED or not term.UNICODE:
            return None
        text_w = max(term.wlen(term.strip_ansi(line)) for line in info)
        for quiet in (4, 3, 2):
            try:
                need_w, need_h = qr.size_in_cells(link, quiet=quiet)
            except Exception:
                return None
            if need_w + text_w + 5 <= cols and need_h + App.FRAME_ROWS <= rows:
                try:
                    return qr.render(link, quiet=quiet)
                except Exception:
                    return None
        return None

    def ensure_account(self):
        acc = self.active_account()
        if not acc:
            ui.message(t("accs.title"), t("run.needacc"))
            self.accounts_screen()
            acc = self.active_account()
            if not acc:
                return None
        if auth.is_expired(acc):
            ui.toast(t("accs.refresh"), kind="warn")
            try:
                acc = auth.refresh(acc, self.cfg.get("ms_client_id", ""))
                self._store_account(acc)
            except Exception as e:
                ui.error(str(e))
                self.accounts_screen()
                return self.active_account()
        return acc

    def play(self, inst):
        already = self.session(inst["id"])
        if already:
            self.watch(already, inst)
            return
        account = self.ensure_account()
        if not account:
            return
        if inst.get("account_id"):
            for acc in self.accounts:
                if acc["id"] == inst["account_id"]:
                    account = acc
        term.clear()
        ui.header(self.header_sub())
        term.out()
        ui.step(t("run.prepare", name=inst["name"]))
        if launch.needs_display():
            ui.toast(t("run.nodisplay"), kind="warn")
        try:
            running = launch.start(inst, self.cfg, account,
                                   keep_log=bool(self.cfg.get("keep_log")))
        except KeyboardInterrupt:
            return
        except Exception as e:
            ui.error(str(e), sub=inst["name"])
            return
        self.cfg["last_instance"] = inst["id"]
        self.cfg.save()
        self.sessions[inst["id"]] = running
        self.watch(running, inst)

    DETACH_KEYS = ("x", "esc", "q")
    STOP_KEYS = ("s",)

    def watch(self, running, inst):
        while running.alive():
            cols, rows = term.size()
            room = max(3, rows - 11)
            lines = running.tail(room)
            lines += [""] * (room - len(lines))
            body = ["  " + ui.dim(term.fit(l, cols - 4)) for l in lines]
            foot = ui.hints(("X", t("run.detach")), ("S", t("inst.stop").lower()))
            if running.log_path:
                foot += "   " + t("run.log", path=os.path.basename(running.log_path))
            ui.frame(t("run.running", name=inst["name"]), self.header_sub(), body,
                     foot + "\n" + t("run.bg"))
            try:
                key = term.wait_key(0.4)
            except KeyboardInterrupt:
                return
            if not key:
                continue
            pressed = term.latin(key)
            if pressed in self.DETACH_KEYS:
                return
            if pressed in self.STOP_KEYS:
                if ui.confirm(t("inst.stop.ask", name=inst["name"])):
                    running.stop()
                    break
        self.sessions.pop(inst["id"], None)
        code = running.code
        text = t("run.ok") if code == 0 else t("run.bad", code=code)
        if code != 0 and running.log_path:
            text += "\n" + t("run.log", path=running.log_path)
        ui.message(inst["name"], text, kind="ok" if code == 0 else "error")

    def settings_screen(self):
        while True:
            cfg = self.cfg
            rows = [
                ui.Row(t("set.lang"), sub=i18n.native_name(i18n.current())),
                ui.Row(t("set.ram"), sub="%d MB" % cfg["ram_mb"]),
                ui.Row(t("set.java"), sub=cfg["java_path"] or t("set.java.auto")),
                ui.Row(t("set.color"), sub=t("on") if cfg["color"] else t("off")),
                ui.Row(t("set.threads"), sub=str(cfg["threads"])),
                ui.Row(t("set.snapshots"), sub=t("on") if cfg["show_snapshots"] else t("off")),
            ]
            if config.SHOW_MICROSOFT:
                rows.append(ui.Row(t("set.msid"), sub=_mask(cfg["ms_client_id"])))
            if config.SHOW_CURSEFORGE:
                rows.append(ui.Row(t("set.cfkey"), sub=_mask(cfg["cf_key"])))
            rows.append(ui.Row(t("set.folder"), sub=paths.ROOT))
            if paths.legacy_root():
                rows.append(ui.Row(t("set.import")))
            rows.append(ui.Row(t("set.about"), sub="%s %s" % (APP, VERSION)))
            action, idx, key = ui.select(t("set.title"), rows, sub=self.header_sub())
            if action != "pick":
                return
            label = rows[idx].label
            if label == t("set.lang"):
                picked = self.choose_language()
                if picked:
                    cfg["lang"] = picked
            elif label == t("set.ram"):
                value = self.pick_ram(cfg["ram_mb"])
                if value:
                    cfg["ram_mb"] = value
            elif label == t("set.java"):
                value = ui.ask(t("set.java"), cfg["java_path"], hint=t("set.java.ask"))
                if value is not None:
                    cfg["java_path"] = value.strip()
            elif label == t("set.color"):
                cfg["color"] = not cfg["color"]
                term.set_color(cfg["color"] and term.color_auto())
            elif label == t("set.threads"):
                value = ui.ask(t("set.threads"), str(cfg["threads"]),
                               allowed=lambda ch: ch.isdigit(), maxlen=2)
                if value and value.isdigit():
                    cfg["threads"] = max(1, min(32, int(value)))
                    net.set_threads(cfg["threads"])
            elif label == t("set.snapshots"):
                cfg["show_snapshots"] = not cfg["show_snapshots"]
            elif label == t("set.msid"):
                value = ui.ask(t("set.msid"), cfg["ms_client_id"], hint=t("set.msid.help"))
                if value is not None:
                    cfg["ms_client_id"] = value.strip()
            elif label == t("set.cfkey"):
                value = ui.ask(t("set.cfkey"), cfg["cf_key"], hint=t("set.cfkey.ask"))
                if value is not None:
                    cfg["cf_key"] = value.strip()
            elif label == t("set.import"):
                self.import_legacy()
            elif label == t("set.about"):
                self.about()
            cfg.save()

    def pick_ram(self, current):
        rows = [ui.Row("%d MB" % v) for v in config.RAM_CHOICES]
        sel = config.RAM_CHOICES.index(current) if current in config.RAM_CHOICES else 3
        action, idx, key = ui.select(t("set.ram"), rows, sel=sel)
        return config.RAM_CHOICES[idx] if action == "pick" else None

    def about(self):
        lines = [
            "%s %s" % (APP, VERSION),
            "",
            t("set.folder") + ": " + paths.ROOT,
            "Java: " + (self.cfg["java_path"] or t("set.java.auto")),
            "Python: %s" % sys.version.split()[0],
            "",
            "Minecraft is a trademark of Mojang AB. This launcher is unofficial.",
        ]
        ui.message(t("set.about"), "\n".join(lines))

    def import_legacy(self):
        old = paths.legacy_root()
        if not old:
            return
        import shutil
        moved = 0
        for name in ("game", "runtime"):
            src = os.path.join(old, name)
            dst = os.path.join(paths.ROOT, name)
            if os.path.isdir(src) and not os.path.isdir(dst):
                shutil.copytree(src, dst)
                moved += 1
        ui.message(t("set.import"), t("set.import.ok") if moved else t("empty"), kind="ok")

    def instance_settings(self, inst):
        while True:
            ram = inst.get("ram_mb")
            size = "%dx%d" % (inst["width"], inst["height"]) if inst["width"] else t("auto")
            account_name = t("is.account.global")
            for acc in self.accounts:
                if acc["id"] == inst.get("account_id"):
                    account_name = acc["name"]
            loader_label = loaders.title(inst["loader"])
            if inst.get("loader_version"):
                loader_label += " " + inst["loader_version"]
            rows = [
                ui.Row("Minecraft", sub=inst["mc"]),
                ui.Row(t("is.loader"), sub=loader_label),
                ui.Row(t("is.ram"), sub="%d MB" % ram if ram else
                       t("is.ram.global", n=self.cfg["ram_mb"])),
                ui.Row(t("is.java"), sub=inst["java_path"] or t("auto")),
                ui.Row(t("is.jvm"), sub=inst["jvm_args"] or t("none")),
                ui.Row(t("is.game"), sub=inst["game_args"] or t("none")),
                ui.Row(t("is.window"), sub=size),
                ui.Row(t("is.fullscreen"), sub=t("on") if inst["fullscreen"] else t("off")),
                ui.Row(t("is.account"), sub=account_name),
                ui.Row(t("is.server"), sub=inst["server"] or t("none")),
                ui.Row(t("is.pre"), sub=inst["pre_cmd"] or t("none")),
                ui.Row(t("is.post"), sub=inst["post_cmd"] or t("none")),
            ]
            action, idx, key = ui.select(t("is.title", name=inst["name"]), rows,
                                    sub=instances.summary(inst))
            if action != "pick":
                instances.save(inst)
                return
            if idx == 0:
                mc = self.pick_version(current=inst["mc"])
                if mc and mc != inst["mc"]:
                    inst["mc"] = mc
                    inst["version_id"] = ""
                    if inst["loader"] != loaders.VANILLA:
                        version = self.pick_loader_version(inst["loader"], mc)
                        inst["loader_version"] = version or ""
                        if not version:
                            inst["loader"] = loaders.VANILLA
            elif idx == 1:
                loader = self.pick_loader(inst["mc"], current=inst["loader"])
                if loader:
                    if loader == loaders.VANILLA:
                        inst["loader"], inst["loader_version"] = loader, ""
                    else:
                        version = self.pick_loader_version(loader, inst["mc"])
                        if version:
                            inst["loader"], inst["loader_version"] = loader, version
                    inst["version_id"] = ""
            elif idx == 2:
                value = self.pick_ram(inst.get("ram_mb") or self.cfg["ram_mb"])
                if value:
                    inst["ram_mb"] = value
            elif idx == 3:
                value = ui.ask(t("is.java"), inst["java_path"], hint=t("set.java.ask"))
                if value is not None:
                    inst["java_path"] = value.strip()
            elif idx == 4:
                value = ui.ask(t("is.jvm"), inst["jvm_args"], hint=t("is.jvm.ask"))
                if value is not None:
                    inst["jvm_args"] = value.strip()
            elif idx == 5:
                value = ui.ask(t("is.game"), inst["game_args"], hint=t("is.game.ask"))
                if value is not None:
                    inst["game_args"] = value.strip()
            elif idx == 6:
                value = ui.ask(t("is.window"), size if inst["width"] else "",
                               hint=t("is.window.ask"))
                if value is not None:
                    inst["width"], inst["height"] = _parse_size(value)
            elif idx == 7:
                inst["fullscreen"] = not inst["fullscreen"]
            elif idx == 8:
                self.pick_instance_account(inst)
            elif idx == 9:
                value = ui.ask(t("is.server"), inst["server"], hint=t("is.server.ask"))
                if value is not None:
                    inst["server"] = value.strip()
            elif idx == 10:
                value = ui.ask(t("is.pre"), inst["pre_cmd"], hint=t("is.cmd.ask"))
                if value is not None:
                    inst["pre_cmd"] = value.strip()
            elif idx == 11:
                value = ui.ask(t("is.post"), inst["post_cmd"], hint=t("is.cmd.ask"))
                if value is not None:
                    inst["post_cmd"] = value.strip()
            instances.save(inst)

    def pick_instance_account(self, inst):
        rows = [ui.Row(t("is.account.global"))]
        ids = [""]
        for acc in self.accounts:
            kind = t("acc.microsoft") if acc["type"] == auth.MICROSOFT else t("acc.offline")
            rows.append(ui.Row(acc["name"], sub=kind))
            ids.append(acc["id"])
        sel = ids.index(inst.get("account_id")) if inst.get("account_id") in ids else 0
        action, idx, key = ui.select(t("is.account"), rows, sel=sel)
        if action == "pick":
            inst["account_id"] = ids[idx]


def _mask(value):
    if not value:
        return t("none")
    return value[:4] + "…" + value[-4:] if len(value) > 10 else "•" * len(value)


def _parse_size(value):
    import re
    found = re.findall(r"\d+", value or "")
    if len(found) >= 2:
        return int(found[0]), int(found[1])
    return 0, 0


def _short_number(n):
    for limit, suffix in ((1000000000, "B"), (1000000, "M"), (1000, "K")):
        if n >= limit:
            return "%.1f%s" % (n / float(limit), suffix)
    return str(n)


def parse_args(argv):
    opts = {"play": None, "list": False, "lang": None, "color": None, "ascii": False,
            "threads": None, "help": False, "version": False}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            opts["help"] = True
        elif arg in ("-V", "--version"):
            opts["version"] = True
        elif arg in ("-l", "--list"):
            opts["list"] = True
        elif arg in ("-p", "--play"):
            nxt = argv[i + 1] if i + 1 < len(argv) else ""
            if nxt and not nxt.startswith("-"):
                opts["play"] = nxt
                i += 1
            else:
                opts["play"] = ""
        elif arg in ("--nocolor", "--no-color"):
            opts["color"] = False
        elif arg == "--ascii":
            opts["ascii"] = True
        elif arg == "--lang" and i + 1 < len(argv):
            opts["lang"] = argv[i + 1]
            i += 1
        elif arg == "--threads" and i + 1 < len(argv):
            opts["threads"] = argv[i + 1]
            i += 1
        elif arg == "--home" and i + 1 < len(argv):
            os.environ["MEOW_HOME"] = argv[i + 1]
            i += 1
        i += 1
    return opts


def quick_launch(app, name):
    inst = instances.by_name(name) if name else None
    if not inst and not name:
        inst = instances.load(app.cfg.get("last_instance") or "")
        if not inst:
            items = instances.list_all()
            inst = items[0] if items else None
    if not inst:
        term.out(t("run.notfound", name=name or "-"))
        return 2
    account = app.active_account()
    if not account:
        term.out(t("run.needacc"))
        return 2
    if auth.is_expired(account):
        try:
            account = auth.refresh(account, app.cfg.get("ms_client_id", ""))
            app._store_account(account)
        except Exception as e:
            term.out(str(e))
            return 2
    ui.toast(t("run.quick", name=inst["name"]))
    running = launch.start(inst, app.cfg, account,
                           keep_log=bool(app.cfg.get("keep_log")), echo=True)
    return running.wait()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = parse_args(argv)

    term.init()
    if opts["ascii"]:
        term.set_unicode(False)
    paths.ensure_dirs()
    i18n.init()

    cfg = config.load()
    term.set_color(term.color_auto() and cfg["color"] and opts["color"] is not False)
    net.set_threads(opts["threads"] or cfg["threads"])
    lang = opts["lang"] or cfg["lang"]
    i18n.set_lang(lang if lang and i18n.has(lang) else i18n.system_lang())

    if opts["help"]:
        term.out(HELP.format(app=APP, ver=VERSION))
        return 0
    if opts["version"]:
        term.out("%s %s" % (APP, VERSION))
        return 0

    app = App(cfg)

    if opts["list"]:
        for inst in instances.list_all():
            term.out("%-24s %s" % (inst["id"], instances.summary(inst)))
        return 0
    if opts["play"] is not None:
        try:
            return quick_launch(app, opts["play"])
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            term.out(str(e))
            return 1

    if not sys.stdin.isatty():
        term.out("%s needs an interactive terminal. Try: %s --play" % (APP, APP))
        return 1

    term.cursor(False)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        term.cursor(True)
        term.set_color(False)
        term.out()
    return 0
