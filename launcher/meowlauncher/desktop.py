import os
import subprocess

from .paths import IS_MAC, IS_WIN


def open_url(url):
    if not url:
        return False
    try:
        import webbrowser
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    try:
        if IS_WIN:
            os.startfile(path)
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def copy_to_clipboard(text):
    if not text:
        return False
    if IS_WIN:
        tools = [["clip"]]
    elif IS_MAC:
        tools = [["pbcopy"]]
    else:
        tools = [["wl-copy"], ["xclip", "-selection", "clipboard"],
                 ["xsel", "--clipboard", "--input"]]
    for tool in tools:
        try:
            done = subprocess.run(tool, input=text.encode("utf-8"), timeout=5,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if done.returncode == 0:
                return True
        except Exception:
            continue
    return False
