#!/usr/bin/env python3
"""Валидатор репозитория savesync-manifests (см. SCHEMA.md §6).

Использование: python tools/validate.py [корень репо]
Выход: 0 — всё чисто, 1 — есть ошибки.
"""
import re
import sys
from pathlib import Path

import yaml

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SLUG_MAX_LEN = 64
KNOWN_PLACEHOLDERS = (
    "<home>", "<winAppData>", "<winLocalAppData>", "<winSavedGames>",
    "<documents>", "<xdgData>", "<xdgConfig>", "<steamCompat>",
)
OS_ENUM = {"windows", "linux", "any"}
TAGS_ENUM = {"save", "config"}
STATUS_ENUM = {"ok", "warn", "blocked"}
SOURCES_ENUM = {"appinfo", "pcgamingwiki", "community"}

errors = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def shard_of(slug: str) -> str:
    return slug[0] if slug[0].isalpha() else "0-9"


def check_rules(path: Path, rules, kind: str) -> None:
    for i, rule in enumerate(rules or []):
        where = f"{kind}[{i}]"
        if not isinstance(rule, dict) or not rule.get("pattern"):
            err(path, f"{where}: отсутствует pattern")
            continue
        pat = rule["pattern"]
        if "\\" in pat:
            err(path, f"{where}: разделитель путей — только '/', не '\\'")
        if kind == "paths":
            ok = pat.startswith(KNOWN_PLACEHOLDERS) or re.match(
                r"^[A-Za-z]:/", pat)
            if not ok:
                err(path, f"{where}: pattern начинается с неизвестного "
                          f"плейсхолдера: {pat!r}")
        if rule.get("os", "any") not in OS_ENUM:
            err(path, f"{where}: недопустимый os={rule.get('os')!r}")
        for t in rule.get("tags", ["save"]):
            if t not in TAGS_ENUM:
                err(path, f"{where}: недопустимый tag={t!r}")


def validate_file(path: Path, slugs: dict, steam_ids: dict) -> None:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        err(path, f"YAML не парсится: {e}")
        return
    if not isinstance(doc, dict):
        err(path, "верхний уровень — не mapping")
        return

    if doc.get("schema") != 1:
        err(path, "schema должен быть 1")

    slug = doc.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.match(slug) \
            or len(slug) > SLUG_MAX_LEN:
        err(path, f"невалидный slug: {slug!r}")
        return
    if path.name != f"{slug}.yaml":
        err(path, f"имя файла {path.name} != {slug}.yaml")
    expected = Path("manifests") / shard_of(slug) / f"{slug}.yaml"
    if path.relative_to(path.parents[2]) != expected:
        err(path, f"файл не в своём шарде, ожидается {expected}")
    if slug in slugs:
        err(path, f"slug {slug!r} уже занят файлом {slugs[slug]}")
    slugs[slug] = path

    if "redirect" in doc:  # заглушка-redirect: дальше не проверяем
        if not SLUG_RE.match(str(doc["redirect"])):
            err(path, f"невалидный redirect slug: {doc['redirect']!r}")
        return

    if not str(doc.get("name") or "").strip():
        err(path, "name обязан быть непустым")

    paths, registry = doc.get("paths"), doc.get("registry")
    if not paths and not registry:
        err(path, "нужно хотя бы одно правило в paths или registry")
    check_rules(path, paths, "paths")
    check_rules(path, registry, "registry")

    port = doc.get("portability") or {}
    status = port.get("status", "ok")
    if status not in STATUS_ENUM:
        err(path, f"недопустимый portability.status={status!r}")
    if status != "ok" and not str(port.get("reason") or "").strip():
        err(path, "portability.status != ok требует непустого reason")

    ids = doc.get("ids") or {}
    for appid in ids.get("steam") or []:
        appid = str(appid)
        if appid in steam_ids:
            err(path, f"steam id {appid} уже у {steam_ids[appid]}")
        steam_ids[appid] = path

    for s in doc.get("sources") or []:
        if s not in SOURCES_ENUM:
            err(path, f"недопустимый source={s!r}")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]
    slugs: dict = {}
    steam_ids: dict = {}
    files = sorted((root / "manifests").rglob("*.yaml"))
    if not files:
        err(root, "нет ни одного манифеста")
    for f in files:
        validate_file(f, slugs, steam_ids)

    bl = root / "blocklist.yaml"
    if bl.exists():
        doc = yaml.safe_load(bl.read_text(encoding="utf-8")) or {}
        for i, e in enumerate(doc.get("entries") or []):
            if e.get("status") not in {"warn", "blocked"}:
                err(bl, f"entries[{i}]: status должен быть warn|blocked")
            if not str(e.get("reason") or "").strip():
                err(bl, f"entries[{i}]: reason обязателен")
            if not (e.get("match") or {}):
                err(bl, f"entries[{i}]: match обязателен")

    for e in errors:
        print(f"ERROR {e}")
    print(f"Проверено манифестов: {len(files)}, ошибок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
