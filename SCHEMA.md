# savesync-manifests — схема репозитория манифестов (schema v1)

> Нормативный документ: формат YAML-файла манифеста, правила slug'ов, структура
> репозитория `savesync-manifests` и правила валидации. Эталонная реализация
> парсера и slug-правил — `crates/core/src/manifest.rs` и
> `crates/core/src/game_key.rs`. Это первый артефакт M1: генератор из Steam
> appinfo, импортер PCGamingWiki и комьюнити-PR обязаны ему соответствовать.

Лицензия репозитория манифестов: **CC BY-NC-SA 4.0**.

---

## 1. Назначение

`savesync-manifests` — собственная база знаний о расположении сохранений игр,
store-агностичная. Рантайм-клиент не ходит ни в какие чужие API: демон работает
со снапшотом этого репозитория (подмодуль/релизный tarball) плюс локальным
парсером Steam appinfo.

Источники наполнения (по приоритету доверия):

1. **Генератор из Steam appinfo** (`appinfo.vdf`, UFS-конфиги) — полностью наш
   источник, покрывает Steam Cloud-пути.
2. **Импортер PCGamingWiki** — пути для не-Steam игр (GOG, Epic, standalone).
3. **Комьюнити-PR** — ручные правки, Proton-маппинги, варн/блок-лист.

---

## 2. Структура репозитория

```
savesync-manifests/
├── README.md
├── LICENSE                     # CC BY-NC-SA 4.0
├── SCHEMA.md                   # этот документ (или ссылка на него)
├── schema/
│   └── manifest.schema.json    # JSON Schema для CI-валидации
├── manifests/
│   ├── e/
│   │   └── elden-ring.yaml     # один файл = одна игра
│   ├── s/
│   │   ├── stardew-valley.yaml
│   │   └── slay-the-spire.yaml
│   └── 0-9/
│       └── 7-days-to-die.yaml  # slug'и, начинающиеся с цифры
├── blocklist.yaml              # глобальный блок/варн-лист (см. §7)
└── .github/workflows/
    └── validate.yml            # CI: schema-валидация каждого PR
```

Правила размещения:

- Один файл = одна игра. Имя файла = `<slug>.yaml`.
- Шардирование по первому символу slug'а: `manifests/<c>/<slug>.yaml`,
  где `<c>` — первая буква (`a`–`z`) или каталог `0-9` для цифр. Одна игра —
  один атомарный PR, без merge-конфликтов в общих файлах.
- Переименование slug'а запрещено после публикации (см. §3): вместо этого
  старый файл заменяется заглушкой `redirect: <new-slug>` минимум на год.

---

## 3. Правила slug'ов

Slug — каноничный идентификатор игры, он же `game_key` в индексе синхронизации.

**Грамматика:**

```
slug = fragment *( "-" fragment )
fragment = 1*( lower_ascii_letter / digit )
```

- Только `[a-z0-9]`, разделитель — одиночный дефис.
- Длина: 1–64 символа (`SLUG_MAX_LEN` в `game_key.rs`).
- Не начинается и не заканчивается дефисом, без `--`.
- Цифра первым символом допустима (`7-days-to-die`).

**Порождение из имени** (эталон — `game_key::slugify`):

1. lowercase; кириллица транслитерируется по встроенной таблице
   (`Ведьмак` → `vedmak`);
2. любая последовательность прочих символов (пробелы, `'`, `:`, `™`, `®`,
   скобки) схлопывается в один дефис;
3. дефисы по краям обрезаются, результат усечён до 64 символов по границе
   фрагмента.

**Коллизии:** если slug занят другой игрой, добавляется уточняющий суффикс:
год (`doom-2016`), затем магазин/издатель, затем числовой `-2`, `-3`.
Генератор обязан проверять уникальность по всему репозиторию.

**Стабильность:** опубликованный slug не меняется (на него ссылаются индексы
устройств пользователей). Опечатки чинятся через `redirect` (см. §2).

**Пользовательские игры** вне базы получают ключ `custom:<slug>` и никогда не
публикуются в репозитории; префикс `custom:` зарезервирован.

---

## 4. Формат YAML-файла (schema v1)

```yaml
schema: 1                        # обязательно, сейчас только 1
name: Elden Ring                 # обязательно, человекочитаемое имя
slug: elden-ring                 # обязательно, = имя файла
aliases:                         # альтернативные написания для матчинга
  - ELDEN RING
ids:                             # магазинные ID (для appinfo-матчинга и UI)
  steam: ["1245620"]
  gog: []
  epic: []
paths:                           # пути сейвов; хотя бы один paths/registry
  - pattern: "<winAppData>/EldenRing/*"
    os: windows                  # windows | linux | any (по умолчанию any)
    tags: [save]                 # save | config; по умолчанию [save]
  - pattern: "<steamCompat>/1245620/pfx/drive_c/users/steamuser/AppData/Roaming/EldenRing"
    os: linux
    tags: [save]
registry:                        # ветки реестра (Windows / Proton *.reg) — см. §7
  - pattern: "HKCU/Software/FromSoftware/ELDENRING"
    os: windows
portability:                     # варн/блок-лист per-game (см. §7)
  status: warn                   # ok (default) | warn | blocked
  reason: "Сейв зашифрован ключом от SteamID64: перенос только между устройствами одного аккаунта"
sources: [appinfo, community]    # appinfo | pcgamingwiki | community
```

### Справка по полям

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `schema` | int | да | Версия схемы, сейчас `1` |
| `name` | string | да | Имя для UI, не пустое |
| `slug` | slug | да | См. §3; обязан совпадать с именем файла |
| `aliases` | [string] | нет | Доп. написания для матчинга пользовательского ввода |
| `ids.steam/gog/epic` | [string] | нет | ID магазинов; Steam appid — ключ Proton-маппинга |
| `paths` | [PathRule] | да* | Пути сейвов (*или `registry`) |
| `paths[].pattern` | string | да | Плейсхолдер + glob (`*`, `**`, `?`) |
| `paths[].os` | enum | нет | `windows` / `linux` / `any` (default) |
| `paths[].tags` | [enum] | нет | `save` (default), `config` |
| `registry` | [PathRule] | нет | Ветки реестра; экспорт в `*.reg` — задача M2+ |
| `portability.status` | enum | нет | `ok` (default) / `warn` / `blocked` |
| `portability.reason` | string | да для warn/blocked | Пояснение пользователю |
| `sources` | [enum] | нет | Откуда запись: `appinfo`, `pcgamingwiki`, `community` |

Неизвестные поля игнорируются (прямая совместимость внутри schema v1).

---

## 5. Плейсхолдеры путей

Первый сегмент `pattern` — плейсхолдер, резолвится демоном per-platform
(`crates/core/src/paths.rs`):

| Плейсхолдер | Windows | Linux / SteamOS |
|---|---|---|
| `<home>` | `C:\Users\<user>` | `~` |
| `<winAppData>` | `%APPDATA%` | — (через `<steamCompat>` для Proton) |
| `<winLocalAppData>` | `%LOCALAPPDATA%` | — |
| `<winSavedGames>` | `Saved Games` профиля | — |
| `<documents>` | `Documents` | `~/Documents` |
| `<xdgData>` | — | `$XDG_DATA_HOME` или `~/.local/share` |
| `<xdgConfig>` | — | `$XDG_CONFIG_HOME` или `~/.config` |
| `<steamCompat>` | — | `<steam-library>/steamapps/compatdata` (каждая библиотека — отдельный кандидат) |

- Плейсхолдер без корня на данной платформе → правило молча пропускается.
- Неизвестный плейсхолдер → правило пропускается (forward-compatible).
- Glob: `*` — в пределах сегмента, `**` — рекурсивно, `?` — один символ.
- Разделитель путей в манифестах — всегда `/`.

---

## 6. Валидация (CI репозитория манифестов)

Каждый PR проверяется (`manifest.schema.json` + скрипт; правила также
реализованы в `Manifest::validate`):

1. `schema: 1`; `slug` валиден по §3 и равен имени файла; файл в правильном шарде.
2. `name` непустое; есть хотя бы одно правило в `paths` или `registry`.
3. Slug уникален по репозиторию; `ids.steam` не пересекаются между играми.
4. `portability.status != ok` требует непустого `reason`.
5. `os` и `tags` — только из перечислений; `pattern` начинается с известного
   плейсхолдера или дискового пути.

Совместимость схемы: добавление полей — без смены версии; изменение смысла
полей или обязательности — `schema: 2` + миграционная заметка в `SCHEMA.md`.

---

## 7. Варн/блок-лист

Два механизма, дополняющих друг друга:

- **Per-game** — поле `portability` в манифесте (см. §4). `blocked` полностью
  исключает игру из синхронизации (UI показывает причину), `warn` — синк с
  предупреждением.
- **Глобальный** `blocklist.yaml` — паттерны по издателю/движку (FromSoftware —
  SteamID64-ключ, GameMaker `secure_save` — machine-lock), применяется до
  per-game полей; per-game запись может сузить, но не отменить глобальный блок.

Сейвы в реестре Proton-префикса (`registry:`) в v1 только описываются —
экспорт/импорт веток `*.reg` реализуется в M2+, до тех пор такие игры
автоматически помечаются `warn`.

---

## 8. Потребление демоном

Демон загружает снапшот репозитория через
`manifest::load_manifest_tree(<snapshot>/manifests)`, валидирует каждую запись
(`Manifest::validate`, ошибки — в лог, запись пропускается) и матчит игры по
`slug` + `ids` + `aliases`. Ручные правила пользователя хранятся отдельно
(`custom:<slug>`) и никогда не перезаписываются обновлением базы.
