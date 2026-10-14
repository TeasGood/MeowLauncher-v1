import collections
import json
import os
import shlex
import subprocess
import threading
import time

from . import auth, instances, java as java_mod, loaders, mojang, net, paths, term, ui
from . import APP, VERSION
from .i18n import t


def needs_display():
    if paths.IS_WIN or paths.IS_MAC:
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def ensure_version(inst, cfg):
    vid = inst.get("version_id")
    if vid and os.path.isfile(mojang.version_file(vid)):
        return vid
    if inst["loader"] == loaders.VANILLA:
        mojang.fetch_version_json(inst["mc"])
        vid = inst["mc"]
    else:
        vid = loaders.install(inst["loader"], inst["mc"], inst["loader_version"], cfg)
    inst["version_id"] = vid
    instances.save(inst)
    return vid


def _ram(inst, cfg):
    return int(inst.get("ram_mb") or cfg.get("ram_mb") or 4096)


def _split_args(raw):
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=not paths.IS_WIN)
    except ValueError:
        return raw.split()


def _quick_play_supported(vj):
    return "quickPlayMultiplayer" in json.dumps(vj.get("arguments", {}))


def build_command(inst, cfg, account, vj, vid, java_exe):
    game_dir = instances.game_dir(inst)
    os.makedirs(game_dir, exist_ok=True)
    natives = os.path.join(mojang.version_dir(vid), "natives")

    classpath, native_jars, tasks = mojang.libraries(vj)
    net.download_many(tasks, t("run.libs"))
    client = mojang.ensure_client(vid, vj)
    mojang.ensure_assets(vj)
    ui.step(t("run.natives"))
    mojang.extract_natives(native_jars, natives)

    width = int(inst.get("width") or 0)
    height = int(inst.get("height") or 0)
    features = {
        "is_demo_user": False,
        "has_custom_resolution": bool(width and height),
        "has_quick_plays_support": bool(inst.get("server")),
        "is_quick_play_multiplayer": bool(inst.get("server")),
        "is_quick_play_singleplayer": False,
        "is_quick_play_realms": False,
    }
    assets_dir = paths.ASSETS
    index_id = (vj.get("assetIndex") or {}).get("id", "legacy")
    ctx = {
        "auth_player_name": account["name"],
        "auth_uuid": account["uuid"].replace("-", ""),
        "auth_access_token": account["access_token"],
        "auth_session": "token:%s:%s" % (account["access_token"],
                                         account["uuid"].replace("-", "")),
        "auth_xuid": account.get("xuid", ""),
        "clientid": cfg.get("ms_client_id", "") or "",
        "user_type": "msa" if account["type"] == auth.MICROSOFT else "legacy",
        "user_properties": "{}",
        "version_name": vid,
        "version_type": vj.get("type", "release"),
        "game_directory": game_dir,
        "assets_root": assets_dir,
        "game_assets": os.path.join(assets_dir, "virtual", "legacy"),
        "assets_index_name": index_id,
        "natives_directory": natives,
        "launcher_name": APP,
        "launcher_version": VERSION,
        "library_directory": paths.LIBRARIES,
        "classpath_separator": os.pathsep,
        "classpath": os.pathsep.join(classpath + [client]),
        "resolution_width": str(width),
        "resolution_height": str(height),
        "quickPlayPath": os.path.join(paths.LOGS, "quickplay.json"),
        "quickPlayMultiplayer": inst.get("server", ""),
        "quickPlaySingleplayer": "",
        "quickPlayRealms": "",
    }

    jvm, main_class, game = mojang.build_args(vj, ctx, features)
    ram = _ram(inst, cfg)
    cmd = [java_exe, "-Xms%dM" % min(512, ram), "-Xmx%dM" % ram, "-XX:+UseG1GC"]
    cmd += _split_args(inst.get("jvm_args"))
    cmd += jvm
    cmd.append(main_class)
    cmd += game
    cmd += _split_args(inst.get("game_args"))
    if inst.get("fullscreen"):
        cmd.append("--fullscreen")
    if inst.get("server") and not _quick_play_supported(vj):
        host, _, port = inst["server"].partition(":")
        cmd += ["--server", host, "--port", port or "25565"]
    return cmd, game_dir


def prepare(inst, cfg, account):
    vid = ensure_version(inst, cfg)
    vj = mojang.resolve(vid)
    major = java_mod.major_for(inst["mc"], vj)
    ui.step(t("run.java", ver=major))
    java_exe = java_mod.ensure(major, inst.get("java_path") or cfg.get("java_path", ""))
    return build_command(inst, cfg, account, vj, vid, java_exe)


class Running(object):

    def __init__(self, proc, inst, game_dir, log_path, keep=200, echo=False):
        self.proc = proc
        self.echo = echo
        self.inst = inst
        self.game_dir = game_dir
        self.log_path = log_path
        self._tail = collections.deque(maxlen=keep)
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        log = None
        if self.log_path:
            try:
                os.makedirs(paths.LOGS, exist_ok=True)
                log = open(self.log_path, "w", encoding="utf-8", errors="replace")
            except OSError:
                log = None
        try:
            for line in self.proc.stdout:
                if log:
                    log.write(line)
                with self._lock:
                    self._tail.append(line.rstrip("\n"))
        finally:
            if log:
                log.close()
        self.proc.wait()
        if self.inst.get("post_cmd"):
            subprocess.call(self.inst["post_cmd"], shell=True, cwd=self.game_dir)

    def tail(self, n):
        with self._lock:
            return list(self._tail)[-n:]

    def alive(self):
        return self.proc.poll() is None

    def stop(self, timeout=10):
        if self.proc.poll() is not None:
            return self.proc.returncode
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout)
        except Exception:
            try:
                self.proc.kill()
                self.proc.wait(5)
            except Exception:
                pass
        return self.proc.returncode

    def wait(self):
        self._thread.join()
        return self.proc.returncode

    @property
    def code(self):
        return self.proc.returncode


def start(inst, cfg, account, keep_log=True, echo=False):
    cmd, game_dir = prepare(inst, cfg, account)
    if inst.get("pre_cmd"):
        subprocess.call(inst["pre_cmd"], shell=True, cwd=game_dir)
    log_path = ""
    if keep_log:
        log_path = os.path.join(paths.LOGS,
                                "%s-%s.log" % (inst["id"], time.strftime("%Y%m%d-%H%M%S")))
    term.out()
    ui.toast(t("run.start", name=inst["name"], nick=account["name"]))
    term.flush()
    proc = subprocess.Popen(cmd, cwd=game_dir, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            errors="replace", bufsize=1)
    instances.mark_played(inst)
    return Running(proc, inst, game_dir, log_path, echo=echo)
