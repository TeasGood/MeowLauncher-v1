#!/usr/bin/env sh
set -e

repo="${MEOW_REPO:-OWNER/REPO}"
branch="${MEOW_BRANCH:-main}"
if [ "$repo" = "OWNER/REPO" ]; then
  echo "Укажите репозиторий: MEOW_REPO=owner/repo"
  exit 1
fi

base="${XDG_DATA_HOME:-$HOME/.local/share}/MeowLauncher/app"
tmp="${TMPDIR:-/tmp}/meowlauncher-install.$$"
mkdir -p "$base" "$tmp"
trap 'rm -rf "$tmp"' EXIT

fetch() {
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
  else echo "Нужен curl или wget."; exit 1; fi
}

echo "Скачиваю MeowLauncher"
fetch "https://codeload.github.com/$repo/tar.gz/refs/heads/$branch" "$tmp/src.tar.gz"
tar -xzf "$tmp/src.tar.gz" -C "$tmp"
src=$(find "$tmp" -maxdepth 2 -type d -name launcher | head -n 1)
if [ -z "$src" ]; then echo "В архиве нет папки launcher."; exit 1; fi

rm -rf "$base/meowlauncher"
cp -R "$src/." "$base/"
chmod +x "$base/MeowLauncher.sh" 2>/dev/null || true

bin="$HOME/.local/bin"
mkdir -p "$bin"
printf '#!/usr/bin/env sh\nexec sh "%s/MeowLauncher.sh" "$@"\n' "$base" > "$bin/meow"
chmod +x "$bin/meow"

echo
echo "Готово. Запуск: meow   (или: sh $base/MeowLauncher.sh)"
echo "Если команда не найдена, добавьте $bin в PATH."
echo

if [ -r /dev/tty ]; then
  exec sh "$base/MeowLauncher.sh" </dev/tty
fi
