#!/usr/bin/env sh
here=$(cd "$(dirname "$0")" && pwd)
script="$here/MeowLauncher.py"
export PYTHONUTF8=1

if [ ! -f "$script" ]; then
  echo "Рядом со скриптом нет MeowLauncher.py."
  exit 1
fi

for p in python3 python; do
  if command -v "$p" >/dev/null 2>&1 && \
     "$p" -c 'import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)' 2>/dev/null; then
    exec "$p" "$script" "$@"
  fi
done

UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ] && command -v uv >/dev/null 2>&1; then UV=$(command -v uv); fi
if [ ! -x "$UV" ]; then
  echo "Python 3.8+ не найден. Поставить uv и Python в домашнюю папку (без root)? [y/N]"
  read -r a
  case "$a" in
    y|Y)
      if command -v curl >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh
      elif command -v wget >/dev/null 2>&1; then wget -qO- https://astral.sh/uv/install.sh | sh
      else echo "Нужен curl или wget."; exit 1; fi
      UV="$HOME/.local/bin/uv" ;;
    *) echo "Установите python3 из пакетного менеджера и запустите снова."; exit 1 ;;
  esac
fi
exec "$UV" run --python 3.12 "$script" "$@"
