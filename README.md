# MeowLauncher

TUI-лаунчер Minecraft: версии с модами, все версии от 1.8.9 до самой свежей,
Fabric / Quilt / Forge / NeoForge, моды с Modrinth живым списком.
Только стандартная библиотека Python 3.8+, без pip, без прав администратора и root.

```
 /\_/\   MeowLauncher 2.0
( o.o )  Steve · офлайн

 Версии

 ▸ ● Ванилла 26.3                           26.3
   ● Фабрик и шейдеры       1.21.1 · Fabric · модов: 14
   ● Технолоджи             1.20.1 · NeoForge · модов: 62
   ● Старое доброе                   1.8.9 · Forge
   ＋ Новая версия

 [Enter] играть  [↑↓] выбор  [/] поиск  [N] новая
 [E] меню  [A] аккаунт  [S] настройки  [Esc] назад
```

## Запуск

```
git clone https://github.com/TeasGood/MeowLauncher-v1.git
cd MeowLauncher-v1
python launcher/MeowLauncher.py
```

Windows без Python: `powershell -ExecutionPolicy Bypass -File launcher\MeowLauncher.ps1`
— скрипт сам найдёт или поставит Python для текущего пользователя.
Linux и macOS: `sh launcher/MeowLauncher.sh`.

При первом запуске лаунчер спросит язык (предложит язык системы, рядом поиск по
списку из 34 языков), потом попросит добавить аккаунт.

## Что умеет

- **Версии.** Игра + загрузчик + моды + свои настройки в отдельной папке.
  У каждой своё имя и свой цвет кота, как в PrismLauncher. Копируются целиком.
  Список игр — все релизы от 1.8.9 до самой свежей, прямо с серверов Mojang;
  снапшоты включаются в настройках.
- **Моды с Modrinth живым списком.** Вкладка модов открывается сразу на самых
  скачиваемых модах для этой версии игры и загрузчика. Пока печатаете название,
  список приходит с Modrinth — запрос уходит, когда вы перестали набирать.
  Зависимости ставятся вместе с модом, включение и выключение одной клавишей.
  Без интернета вкладка честно пишет, что связи нет.
- **Аккаунты.** Офлайн-ник заводится за полминуты.
- **Загрузчики.** Fabric, Quilt, Forge, NeoForge — с выбором конкретной версии.
  Forge и NeoForge ставятся их официальным установщиком.
- **Java.** Нужная версия (8, 17, 21, 25) определяется по json игры и скачивается
  с adoptium.net в папку лаунчера. Системная Java не трогается.
- **Запущенную игру можно оставить или остановить.** Пока она идёт, лаунчер
  показывает её лог; по `X` возвращаетесь к списку версий, а игра продолжает
  работать, по `S` — останавливаете её. В списке такая версия помечена, и
  `Enter` на ней возвращает к той же игре.
- **Расширенные настройки версии.** Память, своя Java, аргументы JVM и игры,
  размер окна, полный экран, сервер для входа при запуске, команды до и после.
- **Быстрый запуск.** `--play «имя версии»` без меню.
- **Терминал.** Текст не вылезает за край окна при любой ширине; `--nocolor`
  убирает цвета, `--ascii` — псевдографику.

## Ключи командной строки

| Ключ | Что делает |
| --- | --- |
| `-p`, `--play [ИМЯ]` | запустить версию сразу; без имени — последнюю |
| `-l`, `--list` | показать версии и выйти |
| `--lang КОД` | язык для этого запуска: `ru`, `en`, `zh-Hans`… |
| `--nocolor` | без цветов и escape-кодов |
| `--ascii` | только ASCII, без псевдографики |
| `--threads N` | сколько файлов качать параллельно (по умолчанию 12) |
| `--home ПАПКА` | другая папка данных |
| `-V`, `--version` | версия |
| `-h`, `--help` | справка |

Переменные окружения: `MEOW_HOME`, `MEOW_LANG`, `MEOW_MS_CLIENT_ID`,
`MEOW_CF_KEY`, `NO_COLOR`.

## Скрытые кнопки: Microsoft и CurseForge

Вход через Microsoft и поиск модов на CurseForge написаны и работают, но их
кнопки убраны из интерфейса: обоим нужен ключ, которого у сборки пока нет.
Код остался на месте, включается двумя флагами в начале
[config.py](launcher/meowlauncher/config.py):

```python
SHOW_MICROSOFT = False
SHOW_CURSEFORGE = False
```

Поставьте `True` — и вернутся: пункт «Войти через Microsoft» в аккаунтах,
«Найти моды на CurseForge» в модах и обе строки с ключами в настройках.

Чтобы вход Microsoft заработал, нужен client ID приложения Azure:
[portal.azure.com](https://portal.azure.com) → App registrations → New
registration → **Public client (mobile & desktop)**, redirect URI
`https://login.microsoftonline.com/common/oauth2/nativeclient`. Подписка и карта
не нужны. ID кладётся в `BUILTIN_MS_CLIENT_ID` в том же файле, в настройки
лаунчера или в `MEOW_MS_CLIENT_ID`. Идентификатор публичного клиента не секрет —
его держат в открытом коде и PrismLauncher, и HMCL.

Ключ CurseForge берётся на [console.curseforge.com](https://console.curseforge.com)
(бесплатно) и кладётся в настройки или в `MEOW_CF_KEY`. В открытый код его
класть нельзя — это запрещено правилами CurseForge.

## Где лежат файлы

```
MeowLauncher/
├─ config.json        язык, память, ключи
├─ accounts.json      аккаунты и сессии
├─ runtime/           Java 8, 17, 21
├─ game/
│  ├─ versions/       версии и загрузчики
│  ├─ libraries/      библиотеки
│  └─ assets/         звуки и текстуры
├─ instances/
│  └─ <версия>/
│     ├─ instance.json
│     └─ minecraft/   saves, options.txt, mods
├─ lang/              свои переводы (*.json)
└─ logs/              логи запусков
```

Windows: `%LOCALAPPDATA%\MeowLauncher` · Linux: `~/.local/share/MeowLauncher` ·
macOS: `~/Library/Application Support/MeowLauncher`. Чтобы удалить всё — сотрите
эту папку.

Переход с MeowCraftLauncher: Настройки → «Перенести из MeowCraftLauncher»,
скачанные версии и Java переедут, качать заново не нужно.

## Структура репозитория

```
launcher/MeowLauncher.py            точка входа
launcher/MeowLauncher.ps1 / .sh     запуск без установленного Python
launcher/meowlauncher/              код лаунчера
launcher/meowlauncher/lang/         переводы, по модулю на язык
MeowLauncher.exe                    собранный лаунчер для Windows
assets/logo.ico                     значок, нужен только для сборки exe
install.ps1, install.sh             установка одной командой
.github/workflows/build.yml         проверки и сборка exe
```

### Собрать exe у себя

```
python -m venv buildenv
buildenv\Scripts\python -m pip install pyinstaller
buildenv\Scripts\python -m PyInstaller --onefile --console --name MeowLauncher ^
    --paths launcher --icon assets\logo.ico launcher\MeowLauncher.py
```

Готовый файл окажется в `dist\MeowLauncher.exe`, около 8 МБ, зависимостей не
требует. На Linux то же самое без `--icon`.

Exe не подписан, поэтому Windows Smart App Control (включён на части свежих
установок Windows 11) его не запустит. Варианты: запускать из исходников,
подписать сертификатом или раздавать пользователям без этой защиты.

### Как добавить язык

Скопируйте `launcher/meowlauncher/lang/en.py` в `<код>.py`, переведите значения,
добавьте код в список `CODES` в `lang/__init__.py`. Полноту набора ключей
проверяет `missing()` из того же модуля (и CI при каждой сборке).

Без правки кода: положите `<код>.json` вида `{"native": "...", "english": "...",
"strings": {...}}` в папку `lang` рядом с данными лаунчера — он подхватится при
следующем запуске.

## Публикация

Репозиторий проекта: [TeasGood/MeowLauncher-v1](https://github.com/TeasGood/MeowLauncher-v1).

1. **Содержимое этой папки кладётся в корень репозитория.** Одного
   `MeowLauncher.py` мало: он всего лишь точка входа и без папки
   `launcher/meowlauncher/` падает с `ModuleNotFoundError`. Работает в одиночку
   только `MeowLauncher.exe` — внутри него уже всё лежит.
2. Кнопка «MeowLauncher.exe» на сайте ведёт прямо на файл в репозитории
   (`raw/main/MeowLauncher.exe`), кнопка с исходниками — на
   `archive/refs/heads/main.zip`. Релиз для этого не нужен.
3. Сборка бинарников: `git tag v2.0 && git push origin v2.0`. GitHub Actions
   соберёт `MeowLauncher.exe` и `MeowLauncher-linux` и приложит к релизу.

**Сайта в репозитории нет.** Его исходники лежат отдельно и заливаются прямо на
хостинг, минуя GitHub: так разметку, тексты и оформление нельзя скачать вместе с
кодом и поднять поддельную копию в пару кликов. GitHub Pages включать не нужно —
ссылки на сайте и так ведут в этот репозиторий. Если сайт понадобится собрать
заново, его файлы лежат у автора в папке `siteMEOW`.

## Оговорки

Неофициальный проект. Не связан с Mojang Studios, Microsoft, Modrinth,
CurseForge, Fabric, Forge и NeoForge. Minecraft — торговая марка Mojang AB.

Код написан с ИИ на 49%, если хотите использовать лаунчер то пользуйтесь.
