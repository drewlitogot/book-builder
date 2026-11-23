#!/usr/bin/env python3
"""Game Package Manager: import, validate, approve and export interactive game ZIPs.

    python tools/games.py validate GAME.zip          check a package without installing it
    python tools/games.py import GAME.zip [--replace] install it (status: review)
    python tools/games.py list                       installed games and their status
    python tools/games.py show ID                    details, warnings and file list
    python tools/games.py approve ID                 mark ready to publish
    python tools/games.py unapprove ID               back to review (removed from the next publish)
    python tools/games.py assign ID CHAPTER          associate the game with another chapter
    python tools/games.py remove ID                  uninstall
    python tools/games.py export ID [--out DIR]      rebuild the ZIP from the installed package
    python tools/games.py prompt CHAPTER             print the AI game-creation prompt for a chapter
    python tools/games.py docs-md                    all Game API docs as one Markdown file (for chat AIs)
    python tools/games.py docs-zip                   zip docs/game-developer for handing to an AI
    python tools/games.py import-reply FILE          import a game from a saved chat reply (files in code blocks)

Packages follow the Book Builder Game Package API 1.1 (docs/game-developer; 1.0 packages still work). Games are installed in
games/packages/ID/ and tracked in games/registry.json. Nothing is approved automatically.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
API_VERSION = "1.1"
SUPPORTED_API = {"1.0", "1.1"}
PLACEHOLDER = re.compile(r"\{\{\s*(answer|var)\s*:\s*([A-Za-z0-9_-]+)\s*\}\}")
DOCS = Path(__file__).resolve().parent.parent / "docs" / "game-developer"   # engine docs, shared by every book
SCHEMAS = DOCS / "schemas"
GAMES = ROOT / "games"
PACKAGES = GAMES / "packages"
STAGING = GAMES / ".staging"
REGISTRY = GAMES / "registry.json"
STATUSES = ("review", "approved", "rejected")

# Archive limits (defence against archive bombs and oversized packages).
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_ENTRIES = 300
MAX_RATIO = 100
MAX_DEPTH = 6

ROOT_FILES = {"game.json", "activity.json", "README.md", "LICENSE", "LICENSE.md", "LICENSE.txt"}
ASSET_TYPES = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
               ".mp3": "audio", ".m4a": "audio", ".ogg": "audio", ".vtt": "captions", ".txt": "transcript"}
IGNORED = re.compile(r"(^|/)(__MACOSX/|\.DS_Store$|Thumbs\.db$|\._)")
SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Editorial lint. These are prompts for a human reviewer, not a content filter: a game that mentions
# one of these may be teaching people to recognise it, which is fine.
MANIPULATION_TERMS = [
    r"\bnegg?ing\b", r"\bpick-?up (line|artist)s?\b", r"\bwear (him|her|them) down\b",
    r"\bmake (him|her|them) jealous\b", r"\buntil (he|she|they) (says?|give in)\b",
    r"\bdon'?t take no\b", r"\bget (him|her|them) to say yes\b", r"\bpush past\b", r"\bguilt (him|her|them)\b",
    r"\bkeep (him|her|them) guessing\b", r"\bplay hard to get\b",
]
LABELING_TERMS = [
    r"\byou (are|might be|may be) (autistic|adhd|a narcissist|codependent|bipolar|borderline)\b",
    r"\byour attachment style is\b", r"\byou have (autism|adhd|bpd|ptsd|cptsd)\b", r"\bdiagnos(e|is|ed)\b",
    r"\byou are an? (introvert|extrovert|empath|avoidant|anxious type)\b",
]
# Chapters where the image rules ask for no images (harassment, abuse, assault, sexual health, crisis).
IMAGE_FREE_CHAPTERS = {32, 33, 34, 35, 36, 55, 57, 59, 60}
SENSITIVE_TERMS = [r"\babuse", r"\bassault", r"\brape\b", r"\btrauma", r"\bsuicid", r"\bself-harm", r"\bcrisis\b",
                   r"\bstalk", r"\bcoercion\b"]


class PackageError(Exception):
    pass


# ------------------------------------------------------------------ helpers

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"apiVersion": API_VERSION, "games": {}}


def save_registry(reg: dict) -> None:
    GAMES.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, REGISTRY)


def book_chapters() -> dict[int, dict]:
    """Numbered chapters from book.yml: {n: {path, title, status}}."""
    manifest = yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for part in manifest.get("parts", []):
        for rel in part["chapters"]:
            m = re.match(r"^(\d+)-", Path(rel).name)
            if not m or "00-front" in rel or "99-back" in rel:
                continue
            p = ROOT / rel
            text = p.read_text(encoding="utf-8") if p.exists() else ""
            fm = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
            meta = (yaml.safe_load(fm.group(1)) or {}) if fm else {}
            out[int(m.group(1))] = {"path": rel, "title": meta.get("title", Path(rel).stem),
                                    "status": meta.get("status", "planned"), "part": part["title"]}
    return out


def semver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ archive safety

def read_archive(data: bytes) -> dict[str, bytes]:
    """Return {posix path: bytes} for a package ZIP, refusing anything unsafe. Never writes to disk."""
    if len(data) > MAX_ZIP_BYTES:
        raise PackageError(f"ZIP is larger than {MAX_ZIP_BYTES // 2**20} MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise PackageError(f"Not a valid ZIP file ({e}).") from e
    infos = [i for i in zf.infolist() if not IGNORED.search(i.filename)]
    if len(infos) > MAX_ENTRIES:
        raise PackageError(f"ZIP has {len(infos)} entries; the limit is {MAX_ENTRIES}.")

    # Many tools zip a folder rather than its contents: accept one wrapping folder.
    names = [i.filename for i in infos if not i.is_dir()]
    prefix = ""
    if "game.json" not in names:
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) == 1 and f"{next(iter(tops))}/game.json" in names:
            prefix = next(iter(tops)) + "/"

    files: dict[str, bytes] = {}
    total = 0
    seen_lower: set[str] = set()
    for info in infos:
        name = info.filename
        if "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise PackageError(f"Unsafe path in ZIP: {name!r}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise PackageError(f"Symbolic links are not allowed: {name}")
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise PackageError(f"Special files are not allowed: {name}")
        if info.flag_bits & 0x1:
            raise PackageError(f"Encrypted entries are not allowed: {name}")
        if info.is_dir():
            continue
        if prefix:
            if not name.startswith(prefix):
                raise PackageError(f"File outside the package folder: {name}")
            name = name[len(prefix):]
        parts = PurePosixPath(name).parts
        if any(p in ("", ".", "..") for p in parts) or not all(SAFE_PART.match(p) for p in parts):
            raise PackageError(f"Unsafe or unsupported file name: {info.filename!r}")
        if len(parts) > MAX_DEPTH:
            raise PackageError(f"Folder nesting too deep: {name}")
        if name.lower() in seen_lower:
            raise PackageError(f"Duplicate file name (names must differ by more than case): {name}")
        seen_lower.add(name.lower())
        if info.file_size > MAX_FILE_BYTES:
            raise PackageError(f"{name} is larger than {MAX_FILE_BYTES // 2**20} MB.")
        if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1_000_000:
            raise PackageError(f"{name} has a suspicious compression ratio (possible archive bomb).")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise PackageError(f"Package expands to more than {MAX_TOTAL_BYTES // 2**20} MB.")
        if name in ROOT_FILES:
            pass
        elif parts[0] == "assets" and len(parts) > 1 and PurePosixPath(name).suffix.lower() in ASSET_TYPES:
            pass
        else:
            raise PackageError(
                f"File not allowed in a game package: {name}. Allowed: game.json, activity.json, README.md, "
                f"LICENSE, and assets/ with {', '.join(sorted(ASSET_TYPES))}. Scripts and HTML are never allowed.")
        # Read with a hard cap, in case the header lies about the size.
        with zf.open(info) as fh:
            content = fh.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES or len(content) != info.file_size:
            raise PackageError(f"{name}: size does not match the ZIP header.")
        files[name] = content
    return files


def sniff(path: str, data: bytes) -> str | None:
    """Check an asset's bytes match its extension. Returns an error or None."""
    ext = PurePosixPath(path).suffix.lower()
    magic = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"), ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".gif": data[:6] in (b"GIF87a", b"GIF89a"),
        ".webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        ".mp3": data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
        ".m4a": data[4:8] == b"ftyp",
        ".ogg": data[:4] == b"OggS",
    }
    if ext in magic and not magic[ext]:
        return f"{path}: contents are not a real {ext[1:].upper()} file."
    if ext in (".vtt", ".txt"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return f"{path}: text files must be UTF-8."
    return None


# ------------------------------------------------------------------ validation

def _json(files: dict[str, bytes], name: str, errors: list[str]) -> dict | None:
    if name not in files:
        errors.append(f"Missing {name} at the top level of the package.")
        return None
    if len(files[name]) > MAX_JSON_BYTES:
        errors.append(f"{name} is larger than 1 MB.")
        return None
    try:
        data = json.loads(files[name].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        errors.append(f"{name} is not valid UTF-8 JSON: {e}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{name} must contain a JSON object.")
        return None
    return data


def _schema_errors(data: dict, name: str, label: str) -> list[str]:
    import jsonschema
    validator = jsonschema.Draft202012Validator(schema(name))
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(top level)"
        out.append(f"{label} {where}: {err.message}")
    return out[:40]


def _walk_conditions(cond, fn) -> None:
    if not isinstance(cond, dict):
        return
    fn(cond)
    for key in ("all", "any"):
        for c in cond.get(key, []):
            _walk_conditions(c, fn)
    if "not" in cond:
        _walk_conditions(cond["not"], fn)


def _texts(activity: dict, manifest: dict):
    """Yield (where, text) for every reader-facing string."""
    for key in ("title", "description"):
        yield f"game.json {key}", manifest.get(key, "")
    for s in activity.get("screens", []):
        sid = s.get("id", "?")
        for key in ("title", "body"):
            yield f"screen {sid} {key}", s.get(key, "")
        for p in s.get("perspectives", []) or []:
            yield f"screen {sid} perspective {p.get('id')}", p.get("body", "")
        for fb in s.get("feedback", []) or []:
            yield f"screen {sid} feedback", fb.get("text", "")
        for i, tk in enumerate(s.get("takeaways", []) or []):
            yield f"screen {sid} takeaway {i + 1}", tk
        for f in s.get("fields", []) or []:
            if f.get("hint"):
                yield f"field {f.get('id')} hint", f["hint"]
        for f in s.get("fields", []) or []:
            yield f"field {f.get('id')} label", f.get("label", "")
            for o in f.get("options", []) or []:
                yield f"field {f.get('id')} option {o.get('value')}", f"{o.get('label', '')} {o.get('feedback', '')}"


def validate_package(files: dict[str, bytes], chapters: dict[int, dict] | None = None) -> dict:
    """Full validation. Returns {ok, errors, warnings, manifest, activity}."""
    errors: list[str] = []
    warnings: list[str] = []
    manifest = _json(files, "game.json", errors)
    activity = _json(files, "activity.json", errors)
    if manifest is None or activity is None:
        return {"ok": False, "errors": errors, "warnings": warnings, "manifest": manifest, "activity": activity}

    for label, data in (("game.json", manifest), ("activity.json", activity)):
        v = data.get("apiVersion")
        if v not in SUPPORTED_API:
            errors.append(f"{label}: apiVersion {v!r} is not supported (this builder supports {', '.join(sorted(SUPPORTED_API))}).")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "manifest": manifest, "activity": activity}
    errors += _schema_errors(manifest, "game", "game.json")
    errors += _schema_errors(activity, "activity", "activity.json")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "manifest": manifest, "activity": activity}

    # Chapter association.
    chapters = book_chapters() if chapters is None else chapters
    ch = chapters.get(manifest["chapter"])
    if not ch:
        errors.append(f"game.json chapter: chapter {manifest['chapter']} does not exist in book.yml.")
    elif ch["status"] != "approved":
        warnings.append(f"Chapter {manifest['chapter']} is not approved yet, so this game can't be published until it is.")

    # Assets: declared ⇔ present, types match, alt text, transcripts.
    declared = {a["path"]: a for a in manifest["assets"]}
    present = {p for p in files if p.startswith("assets/")}
    for p in sorted(present - declared.keys()):
        errors.append(f"{p} is in the ZIP but not listed in game.json assets.")
    for p, a in declared.items():
        if p not in files:
            errors.append(f"game.json assets lists {p}, which is not in the ZIP.")
            continue
        expected = ASSET_TYPES.get(PurePosixPath(p).suffix.lower())
        if expected != a["type"]:
            errors.append(f"{p}: type {a['type']!r} doesn't match the file extension (expected {expected!r}).")
        if (e := sniff(p, files[p])):
            errors.append(e)
        if a["type"] == "image" and "alt" not in a:
            errors.append(f"{p}: images need alt text (use \"\" only for decorative images).")
        if a["type"] == "audio":
            t = a.get("transcript")
            if not t or t not in declared or declared[t]["type"] != "transcript":
                errors.append(f"{p}: audio needs a transcript asset (\"transcript\": \"assets/....txt\").")
    caps = set(manifest["requiredCapabilities"])
    icon = manifest.get("icon")
    if icon is not None and (declared.get(icon) or {}).get("type") != "image":
        errors.append(f"game.json icon: {icon} must be listed in assets as an image.")
    image_free = bool(manifest.get("sensitive")) or manifest["chapter"] in IMAGE_FREE_CHAPTERS
    scene_images = [p_ for p_, a in declared.items() if a["type"] == "image" and p_ != icon]
    if manifest.get("apiVersion") == "1.1" and not image_free:
        if not icon:
            warnings.append("House style: add a square icon (\"icon\": \"assets/icon.png\", declared as an image asset).")
        if len(scene_images) < SCENE_IMAGES:
            warnings.append(f"House style: {len(scene_images)} scene image(s); games normally have {SCENE_IMAGES} "
                            "(two sheets of four).")
        elif len(scene_images) % SHEET_PANELS:
            warnings.append(f"{len(scene_images)} scene images don't fill whole sheets of {SHEET_PANELS}; "
                            "the extra ones have to be attached one by one.")
    if scene_images and image_free:
        warnings.append("Editorial review: this game has images but covers a sensitive topic (harassment, abuse, "
                        "assault, sexual health or crisis). The image rules say to use no images here.")
    if any(a["type"] == "image" for a in declared.values()) and "images" not in caps:
        warnings.append("Package has images but doesn't list the \"images\" capability.")
    if any(a["type"] == "audio" for a in declared.values()) and "audio" not in caps:
        errors.append("Package has audio but doesn't list the \"audio\" capability.")

    # Screens, fields, references.
    screens = activity["screens"]
    ids = [s["id"] for s in screens]
    by_id = {s["id"]: s for s in screens}
    for d in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"Screen id {d!r} is used more than once.")
    if activity["start"] not in by_id:
        errors.append(f"start screen {activity['start']!r} does not exist.")
    variables = set((activity.get("variables") or {}).keys())
    field_ids: list[str] = []
    field_by_id: dict[str, dict] = {}
    for s in screens:
        for f in s.get("fields", []) or []:
            field_ids.append(f["id"])
            field_by_id[f["id"]] = f
    for d in {i for i in field_ids if field_ids.count(i) > 1}:
        errors.append(f"Field id {d!r} is used more than once (field ids must be unique across the activity).")
    scored_total = sum(1 for f in field_by_id.values() if f.get("scored"))

    # API 1.1 features need apiVersion 1.1 in both files (an older runtime wouldn't understand them).
    v11: list[str] = []

    def check_cond(where: str):
        def fn(c: dict) -> None:
            if "score" in c or "first" in c:
                v11.append(f"{where}: the {'score' if 'score' in c else 'first'} condition")
            if "score" in c:
                if scored_total == 0:
                    errors.append(f"{where}: a score condition needs scored questions in the activity.")
                return
            if "first" in c and "field" in c and (field_by_id.get(c["field"]) or {}).get("type") != "ranking":
                errors.append(f"{where}: \"first\" only works on ranking fields.")
            leaf_ops = [k for k in c if k not in ("field", "var", "all", "any", "not", "visited")]
            if "field" in c:
                if c["field"] not in field_by_id:
                    errors.append(f"{where}: condition refers to unknown field {c['field']!r}.")
                if len(leaf_ops) != 1:
                    errors.append(f"{where}: a field condition needs exactly one operator (equals, in, includes, gte, answered, ...).")
            elif "var" in c:
                if c["var"] not in variables:
                    errors.append(f"{where}: condition refers to undeclared variable {c['var']!r}.")
                if len(leaf_ops) != 1:
                    errors.append(f"{where}: a variable condition needs exactly one operator.")
            elif "visited" in c:
                if c["visited"] not in by_id:
                    errors.append(f"{where}: condition refers to unknown screen {c['visited']!r}.")
        return fn

    def check_effects(where: str, effects) -> None:
        for e in effects or []:
            if e["var"] not in variables:
                errors.append(f"{where}: effect changes undeclared variable {e['var']!r}.")
            elif "add" in e and not isinstance(activity["variables"][e["var"]]["initial"], (int, float)):
                errors.append(f"{where}: \"add\" needs a numeric variable ({e['var']!r} isn't).")

    def check_placeholders(where: str, text: str) -> None:
        for kind_, name in PLACEHOLDER.findall(text or ""):
            v11.append(f"{where}: {{{{{kind_}:{name}}}}}")
            if kind_ == "answer" and name not in field_by_id:
                errors.append(f"{where}: {{{{answer:{name}}}}} refers to unknown field {name!r}.")
            if kind_ == "var" and name not in variables:
                errors.append(f"{where}: {{{{var:{name}}}}} refers to undeclared variable {name!r}.")
        for bad in re.findall(r"\{\{[^}]*\}\}", text or ""):
            if not PLACEHOLDER.fullmatch(bad):
                errors.append(f"{where}: {bad} isn't a valid placeholder (use {{{{answer:fieldId}}}} or {{{{var:name}}}}).")

    for s in screens:
        check_placeholders(f"screen {s['id']} title", s.get("title", ""))
        check_placeholders(f"screen {s['id']} body", s.get("body", ""))
        for p_ in s.get("perspectives", []) or []:
            check_placeholders(f"screen {s['id']} perspective {p_['id']}", p_.get("body", ""))
        for fb in s.get("feedback", []) or []:
            check_placeholders(f"screen {s['id']} feedback", fb.get("text", ""))
        for i, tk in enumerate(s.get("takeaways", []) or []):
            check_placeholders(f"screen {s['id']} takeaway {i + 1}", tk)
        if s.get("takeaways"):
            v11.append(f"screen {s['id']}: takeaways")
        if s.get("allowSaveNotes"):
            v11.append(f"screen {s['id']}: allowSaveNotes")
            if "save-notes" not in caps:
                errors.append(f"screen {s['id']} offers Save my notes; add \"save-notes\" to requiredCapabilities.")
        if s["type"] != "completion" and (s.get("takeaways") or s.get("allowSaveNotes")):
            errors.append(f"screen {s['id']}: takeaways and allowSaveNotes are only for completion screens.")
        if s["type"] == "completion" and s.get("feedback"):
            v11.append(f"screen {s['id']}: completion feedback")
        if s["type"] not in ("form", "completion") and s.get("feedback"):
            errors.append(f"screen {s['id']}: feedback rules are only for form and completion screens.")
        for f in s.get("fields", []) or []:
            if f["type"] == "ranking":
                v11.append(f"field {f['id']}: ranking")
                if len(f.get("options") or []) > 8:
                    errors.append(f"field {f['id']}: ranking fields can have at most 8 options.")
                if f.get("scored") or any(o.get("feedback") or o.get("effects") for o in f.get("options") or []):
                    errors.append(f"field {f['id']}: ranking options can't be scored or carry feedback or effects; "
                                  "use screen feedback rules with the \"first\" condition instead.")
            if f.get("shuffle"):
                v11.append(f"field {f['id']}: shuffle")
                if f["type"] not in ("single-choice", "multiple-choice", "cards", "ranking"):
                    errors.append(f"field {f['id']}: shuffle works on single-choice, multiple-choice, cards and ranking fields.")
            if f.get("hint"):
                v11.append(f"field {f['id']}: hint")
    if "icon" in manifest:
        v11.append("game.json icon")
    used = set()
    for s in screens:
        if s.get("image"):
            used.add(s["image"]["asset"])
        for p_ in s.get("perspectives", []) or []:
            if p_.get("image"):
                used.add(p_["image"]["asset"])
    for p_ in scene_images:
        if p_ not in used:
            warnings.append(f"{p_} is declared but no screen or perspective shows it.")

    scored_fields = 0
    for s in screens:
        sid = s["id"]
        nxt = s.get("next")
        targets = [nxt] if isinstance(nxt, str) else ([r["goto"] for r in nxt.get("rules", [])] + [nxt["default"]] if nxt else [])
        for t in targets:
            if t not in by_id:
                errors.append(f"screen {sid}: next goes to unknown screen {t!r}.")
        if isinstance(nxt, dict):
            for r in nxt.get("rules", []):
                _walk_conditions(r["when"], check_cond(f"screen {sid} next"))
            if nxt.get("rules"):
                caps_needed = "branching"
                if caps_needed not in caps:
                    warnings.append(f"screen {sid} branches; add \"branching\" to requiredCapabilities.")
        for fb in s.get("feedback", []) or []:
            _walk_conditions(fb.get("when"), check_cond(f"screen {sid} feedback"))
        check_effects(f"screen {sid}", s.get("effects"))
        if s.get("image"):
            a = declared.get(s["image"]["asset"])
            if not a or a["type"] != "image":
                errors.append(f"screen {sid}: image {s['image']['asset']} is not a declared image asset.")
        for p in s.get("perspectives", []) or []:
            if p.get("image") and (declared.get(p["image"]["asset"]) or {}).get("type") != "image":
                errors.append(f"screen {sid}: image {p['image']['asset']} is not a declared image asset.")
        if s["type"] == "perspective" and "perspective-switching" not in caps:
            warnings.append(f"screen {sid} is a perspective screen; add \"perspective-switching\" to requiredCapabilities.")
        if s.get("showSummary") and "reflection-summary" not in caps:
            warnings.append(f"screen {sid} shows a summary; add \"reflection-summary\" to requiredCapabilities.")
        earlier = set()
        for f in s.get("fields", []) or []:
            fid = f["id"]
            if f.get("showIf"):
                _walk_conditions(f["showIf"], check_cond(f"field {fid} showIf"))
                def same_screen_later(c, fid=fid, earlier=frozenset(earlier), here={x["id"] for x in s["fields"]}):
                    if "field" in c and c["field"] in here and c["field"] not in earlier:
                        errors.append(f"field {fid}: showIf can only depend on fields above it.")
                _walk_conditions(f["showIf"], same_screen_later)
            earlier.add(fid)
            opts = f.get("options") or []
            vals = [o["value"] for o in opts]
            if len(vals) != len(set(vals)):
                errors.append(f"field {fid}: option values must be unique.")
            for o in opts:
                check_effects(f"field {fid} option {o['value']}", o.get("effects"))
            if f["type"] == "slider":
                if f["min"] >= f["max"]:
                    errors.append(f"field {fid}: slider min must be less than max.")
                if not (f.get("minLabel") and f.get("maxLabel")):
                    warnings.append(f"field {fid}: sliders should have minLabel and maxLabel so the scale is clear.")
            if f.get("minSelected") and f.get("maxSelected") and f["minSelected"] > f["maxSelected"]:
                errors.append(f"field {fid}: minSelected is larger than maxSelected.")
            has_correct = any(o.get("correct") for o in opts)
            if f.get("scored"):
                scored_fields += 1
                if f["type"] not in ("single-choice", "multiple-choice", "dropdown", "cards"):
                    errors.append(f"field {fid}: only choice fields (not ranking) can be scored.")
                if not has_correct:
                    errors.append(f"field {fid}: scored fields need at least one option with \"correct\": true.")
            elif has_correct:
                errors.append(f"field {fid}: \"correct\" is only allowed on scored fields.")

    if v11 and (manifest["apiVersion"] != "1.1" or activity["apiVersion"] != "1.1"):
        errors.append("These need \"apiVersion\": \"1.1\" in both game.json and activity.json: "
                      + "; ".join(sorted(set(v11))[:8]) + ("…" if len(set(v11)) > 8 else ""))

    # Reachability and completion.
    if activity["start"] in by_id:
        seen, stack = set(), [activity["start"]]
        while stack:
            sid = stack.pop()
            if sid in seen or sid not in by_id:
                continue
            seen.add(sid)
            nxt = by_id[sid].get("next")
            if isinstance(nxt, str):
                stack.append(nxt)
            elif isinstance(nxt, dict):
                stack += [r["goto"] for r in nxt.get("rules", [])] + [nxt["default"]]
        for sid in ids:
            if sid not in seen:
                warnings.append(f"screen {sid} can never be reached from the start screen.")
        if not any(by_id[s]["type"] == "completion" for s in seen):
            errors.append("No completion screen can be reached from the start screen.")
        # Every reachable screen must be able to reach a completion screen (no dead loops).
        def reaches_end(sid: str, path: frozenset = frozenset()) -> bool:
            if by_id[sid]["type"] == "completion":
                return True
            if sid in path:
                return False
            nxt = by_id[sid].get("next")
            ts = [nxt] if isinstance(nxt, str) else [r["goto"] for r in nxt.get("rules", [])] + [nxt["default"]]
            return any(t in by_id and reaches_end(t, path | {sid}) for t in ts)
        for sid in seen:
            if not reaches_end(sid):
                errors.append(f"screen {sid}: no path from here leads to a completion screen.")

    # Editorial rules (research/02-editorial-charter.md).
    kind = manifest["activityType"]
    text = [(w, t) for w, t in _texts(activity, manifest) if t]
    sensitive_topic = any(re.search(p, t, re.I) for _, t in text for p in SENSITIVE_TERMS)
    if scored_fields and kind != "knowledge-check":
        errors.append("Only knowledge-check activities may use right/wrong scoring. Interpersonal scenarios and "
                      "reflections use nuanced feedback instead.")
    if scored_fields and "scoring" not in caps:
        warnings.append("Package has scored fields; add \"scoring\" to requiredCapabilities.")
    if manifest.get("sensitive"):
        if scored_fields:
            errors.append("Sensitive activities (trauma, abuse, crisis) must be ungraded.")
        if not manifest["contentWarnings"]:
            errors.append("Sensitive activities need at least one content warning.")
        for s in screens:
            for f in s.get("fields", []) or []:
                if f.get("required"):
                    errors.append(f"field {f['id']}: sensitive activities can't make answers required.")
    elif sensitive_topic:
        warnings.append("The text mentions abuse, assault, trauma or crisis but the game isn't marked "
                        "\"sensitive\": true. Check whether it should be (ungraded, content warnings).")
    for where, t in text:
        for p in MANIPULATION_TERMS:
            if re.search(p, t, re.I):
                warnings.append(f"Editorial review: {where} mentions {re.search(p, t, re.I).group(0)!r}. "
                                "Make sure it is recognized as harmful, never taught as a tactic.")
        if kind == "reflection" or "feedback" in where or "option" in where:
            for p in LABELING_TERMS:
                if re.search(p, t, re.I):
                    warnings.append(f"Editorial review: {where} says {re.search(p, t, re.I).group(0)!r}. "
                                    "Games must not assign diagnoses or personality labels.")
        if re.search(r"<\s*(script|iframe|style|img|a)\b|javascript:|on\w+\s*=", t, re.I):
            errors.append(f"{where}: HTML and scripts are not allowed in text. Use the Markdown subset.")
        for url in re.findall(r"\]\(([^)]*)\)", t):
            if not url.startswith("https://"):
                errors.append(f"{where}: links must use https:// ({url!r}).")
    for s in screens:
        for f in s.get("fields", []) or []:
            if f["type"] in ("text", "textarea") and f.get("required"):
                warnings.append(f"field {f['id']}: written answers should be optional so readers can skip.")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "manifest": manifest, "activity": activity}


# ------------------------------------------------------------------ install, update, remove

def package_hash(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(files[name]).digest())
    return h.hexdigest()


def install(data: bytes, replace: bool = False, source: str = "") -> dict:
    """Validate and atomically install a package. Raises PackageError with a readable message."""
    import jobs as J
    J.report(0.05, "Reading the package…")
    files = read_archive(data)
    J.report(0.25, "Validating game.json, activity.json and assets…")
    result = validate_package(files)
    J.report(0.6, "Checking it against the installed games…")
    if not result["ok"]:
        raise PackageError("Package is not valid:\n- " + "\n- ".join(result["errors"]))
    m = result["manifest"]
    gid, version = m["id"], m["version"]
    digest = package_hash(files)
    reg = load_registry()
    old = reg["games"].get(gid)
    if old:
        if old["sha256"] == digest:
            raise PackageError(f"{gid} {version} is already installed with identical contents.")
        if not replace:
            raise PackageError(f"A game with id {gid!r} is already installed (version {old['version']}). "
                               "Use Replace/Update to install the new package over it.")
        if semver(version) < semver(old["version"]):
            raise PackageError(f"{gid}: version {version} is older than the installed {old['version']}. "
                               "Raise the version number in game.json.")
        if semver(version) == semver(old["version"]):
            raise PackageError(f"{gid}: version {version} is already installed with different contents. "
                               "Raise the version number in game.json for an updated package.")

    # Stage the files, then swap the folder in with a rename (atomic on one filesystem).
    J.report(0.7, "Installing…")
    STAGING.mkdir(parents=True, exist_ok=True)
    stage = STAGING / f"{gid}-{uuid.uuid4().hex[:8]}"
    backup = None
    target = PACKAGES / gid
    try:
        for name, content in files.items():
            dest = stage / name
            if not dest.resolve().is_relative_to(stage.resolve()):
                raise PackageError(f"Unsafe path: {name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "xb") as fh:  # never overwrite
                fh.write(content)
        PACKAGES.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = STAGING / f"{gid}-previous-{uuid.uuid4().hex[:8]}"
            os.replace(target, backup)
        os.replace(stage, target)
        entry = {
            "id": gid, "title": m["title"], "version": version, "chapter": m["chapter"],
            "activityType": m["activityType"], "subjects": m.get("subjects", []),
            "status": "review", "sha256": digest, "installedAt": now(), "approvedAt": None,
            "source": source, "warnings": result["warnings"],
            "history": ((old or {}).get("history", []) + ([{"version": old["version"], "replacedAt": now()}] if old else [])),
        }
        reg["games"][gid] = entry
        save_registry(reg)
    except Exception:
        # Roll back: remove the half-installed copy and restore the previous version.
        shutil.rmtree(stage, ignore_errors=True)
        if backup and backup.exists():
            shutil.rmtree(target, ignore_errors=True)
            os.replace(backup, target)
        raise
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
    J.report(1.0, f"Installed {gid} {version}")
    return {"entry": entry, "warnings": result["warnings"], "replaced": bool(old)}


def get(gid: str) -> dict:
    reg = load_registry()
    if gid not in reg["games"]:
        raise PackageError(f"No installed game with id {gid!r}.")
    return reg["games"][gid]


def set_status(gid: str, status: str) -> dict:
    assert status in STATUSES
    reg = load_registry()
    g = reg["games"].get(gid)
    if not g:
        raise PackageError(f"No installed game with id {gid!r}.")
    if status == "approved":
        files = installed_files(gid)
        res = validate_package(files)
        if not res["ok"]:
            raise PackageError("Can't approve: the installed package no longer validates:\n- " + "\n- ".join(res["errors"]))
        if package_hash(files) != g["sha256"]:
            raise PackageError("Can't approve: installed files were changed after import. Re-import the package.")
    g["status"] = status
    g["approvedAt"] = now() if status == "approved" else None
    save_registry(reg)
    return g


def assign(gid: str, chapter: int) -> dict:
    """Associate a game with another chapter: rewrites the installed game.json and resets to review."""
    g = get(gid)
    if chapter not in book_chapters():
        raise PackageError(f"Chapter {chapter} does not exist.")
    path = PACKAGES / gid / "game.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["chapter"] = chapter
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    reg = load_registry()
    reg["games"][gid].update(chapter=chapter, status="review", approvedAt=None,
                             sha256=package_hash(installed_files(gid)))
    save_registry(reg)
    return reg["games"][gid]


def remove(gid: str) -> None:
    reg = load_registry()
    if gid not in reg["games"]:
        raise PackageError(f"No installed game with id {gid!r}.")
    shutil.rmtree(PACKAGES / gid, ignore_errors=True)
    del reg["games"][gid]
    save_registry(reg)


def installed_files(gid: str) -> dict[str, bytes]:
    base = PACKAGES / gid
    if not base.is_dir():
        raise PackageError(f"Package folder for {gid} is missing.")
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_symlink():
            raise PackageError(f"Symlink in installed package: {p}")
        if p.is_file():
            out[p.relative_to(base).as_posix()] = p.read_bytes()
    return out


def export(gid: str, out_dir: Path | None = None) -> Path:
    g = get(gid)
    out_dir = out_dir or ROOT / "dist" / "game-exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{gid}-{g['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in installed_files(gid).items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
    return out


def published_games(chapters: dict[int, dict] | None = None) -> list[dict]:
    """Approved games whose chapter is approved and whose files still match what was approved."""
    chapters = book_chapters() if chapters is None else chapters
    out = []
    for g in load_registry()["games"].values():
        if g["status"] != "approved":
            continue
        if chapters.get(g["chapter"], {}).get("status") != "approved":
            continue
        try:
            if package_hash(installed_files(g["id"])) != g["sha256"]:
                continue
        except PackageError:
            continue
        out.append(g)
    return sorted(out, key=lambda g: (g["chapter"], g["title"]))


# ------------------------------------------------------------------ prompts

def api_essentials() -> str:
    """The minimum an AI needs to build a valid package, generated from the schemas and templates so
    it can't drift from what the validator enforces. Appended to every copied prompt."""
    gs, acts = schema("game"), schema("activity")
    d = acts["$defs"]
    tpl = DOCS / "templates"
    enum = lambda xs: ", ".join(f"`{x}`" for x in xs)
    return f"""## API essentials (Game Package API {API_VERSION})

Everything below is enforced by the Book Manager's validator. A package that breaks any of it is rejected.

**game.json required fields:** {enum(gs["required"])}. No other fields than: {enum(gs["properties"].keys())}.
- `accessibility` must have `summary` (10–400 characters), `"keyboard": true` and `"screenReader": true`.
- `learningObjectives`: 1–6 strings. `authors`: at least one `{{"name": "..."}}`. `assets`: `[]` if none.
- `activityType`: {enum(gs["properties"]["activityType"]["enum"])}.
- `requiredCapabilities` (list every one you use): {enum(gs["properties"]["requiredCapabilities"]["items"]["enum"])}.
- `id`: lowercase, digits and hyphens, e.g. `ch07-what-i-want`. `version`: `1.0.0`. `chapter`: the chapter number.
- Images: 8 scene images `assets/img-01-<name>.webp` … `img-08-…` declared in sheet panel order, then
  `{{"path": "assets/icon.png", "type": "image", "alt": "..."}}` and `"icon": "assets/icon.png"`. Each is used with
  `"image": {{"asset": "assets/img-01-<name>.webp"}}` on a screen or perspective, plus `"images"` in
  requiredCapabilities. Follow "Image style for Book Builder games" above for look, sheets and delivery.

**activity.json:** `{{"apiVersion": "{API_VERSION}", "start": "<first screen id>", "variables": {{...optional}}, "screens": [...]}}`
- Screen `type`: {enum(d["screen"]["properties"]["type"]["enum"])}. Every screen has `id`, `type`, `title`;
  every type except `completion` needs `next`; `form` needs `fields`; `perspective` needs 2–6 `perspectives`.
- Field `type`: {enum(d["field"]["properties"]["type"]["enum"])}. Choice fields need 2–12 `options`
  (`value`, `label`, optional `description`, `feedback`, `tone`, `effects`); sliders need `min` and `max`.
- Feedback `tone`: {enum(d["tone"]["enum"])}. Scoring (`"scored": true` + `"correct": true`) only in `knowledge-check`.
- `next` is a screen id, or `{{"rules": [{{"when": <condition>, "goto": "<id>"}}], "default": "<id>"}}`.
- Conditions: `{{"field": "<id>", "equals": "<value>"}}`; other operators `notEquals`, `in`, `includes`,
  `gt`, `gte`, `lt`, `lte`, `answered`; `{{"var": ...}}`, `{{"visited": "<screen id>"}}`, `all`, `any`, `not`.
- Text fields (`body`, `feedback`, perspective `body`): plain text, `**bold**`, `*italic*`, `- ` lists,
  `[links](https://...)`. No HTML.
- Every path must reach a `completion` screen. Ids must be unique; every referenced id must exist.

**New in API {API_VERSION}** (use `"apiVersion": "{API_VERSION}"` in both files when you use any of these):
- Personalized text: `{{{{answer:<fieldId>}}}}` and `{{{{var:<name>}}}}` in titles, bodies, feedback and takeaways
  insert the reader's answer (option label, or what they typed) or a variable's value.
- `"type": "ranking"`: the reader puts 2–8 options in order (value: the option values, first = most).
  Not scorable; react to it with screen feedback rules using `{{"field": "<id>", "first": "<value>"}}`.
- `"shuffle": true` on single-choice, multiple-choice, cards and ranking fields; `"hint": "..."` on any field.
- Completion screens: `"feedback"` rules pick the result to show (e.g. by variable or by
  `{{"score": {{"gte": 0.8}}}}`, the share of scored questions answered as the book suggests);
  `"takeaways": ["...", ...]` (1–8 short points); `"allowSaveNotes": true` adds a "Save my notes" button
  that downloads the reader's answers and takeaways to their own device (add `"save-notes"` to requiredCapabilities).

**A complete, valid game.json** (structure to copy; change every value):

```json
{(tpl / "minimal-package" / "game.json").read_text(encoding="utf-8").strip()}
```

**A complete, valid activity.json** showing branching, a perspective screen, a slider and a conditional field:

```json
{(tpl / "branching-package" / "activity.json").read_text(encoding="utf-8").strip()}
```
**A complete, valid API {API_VERSION} activity.json** showing a ranking, personalized text, a hint, feedback on
the top-ranked choice, takeaways and Save my notes:

```json
{(tpl / "reflection-package" / "activity.json").read_text(encoding="utf-8").strip()}
```
"""


def image_style() -> str:
    """The single image style guide, pasted into every game prompt so all games share one look."""
    return re.sub(r"^#", "##", (DOCS / "image-style.md").read_text(encoding="utf-8").strip(), flags=re.M)


def creation_prompt(chapter: int | None) -> str:
    base = (DOCS / "ai-game-creation-prompt.md").read_text(encoding="utf-8")
    essentials = "\n\n---\n\n" + image_style() + "\n\n---\n\n" + api_essentials()
    if chapter is None:
        return base + essentials
    ch = book_chapters().get(chapter)
    if not ch:
        raise PackageError(f"Chapter {chapter} does not exist.")
    body = (ROOT / ch["path"]).read_text(encoding="utf-8")
    body = re.sub(r"\A---.*?\n---\s*\n", "", body, flags=re.S)
    existing = [g for g in load_registry()["games"].values() if g["chapter"] == chapter]
    taken = ", ".join(f"{g['id']} ({g['version']})" for g in existing) or "none"
    return (f"{base}{essentials}\n\n---\n\n## This request\n\n"
            f"- Chapter number: **{chapter}**\n- Chapter title: **{ch['title']}**\n"
            f"- Chapter status: {ch['status']}\n- Game ids already used for this chapter: {taken}\n"
            f"- Suggested id: `ch{chapter:02d}-` followed by two to four words, for example `ch{chapter:02d}-practice`\n\n"
            f"## The chapter (approved text)\n\n{body.strip()}\n")


def update_prompt(gid: str) -> str:
    """Ask ChatGPT to bring an installed game up to the current API and image style, keeping what works."""
    entry = get(gid)
    files = installed_files(gid)
    manifest = json.loads(files["game.json"])
    ch = book_chapters().get(manifest["chapter"]) or {}
    body = ""
    if ch.get("path") and (ROOT / ch["path"]).exists():
        body = re.sub(r"\A---.*?\n---\s*\n", "", (ROOT / ch["path"]).read_text(encoding="utf-8"), flags=re.S).strip()
    major, minor, patch = (list(semver(entry["version"])) + [0, 0, 0])[:3]
    next_version = f"{major}.{minor + 1}.0"
    images = [a for a in manifest.get("assets", []) if a.get("type") == "image"]
    blocks = "\n\n".join(f"**{name}**\n```{'json' if name.endswith('.json') else 'markdown'}\n"
                          f"{files[name].decode('utf-8').strip()}\n```" for name in ("game.json", "activity.json", "README.md")
                          if name in files)
    base = (DOCS / "ai-game-creation-prompt.md").read_text(encoding="utf-8")
    return f"""# Update a Book Builder game to Game API {API_VERSION}

CHAT NAME: Game update · {gid}

You are updating an existing interactive activity for a book. The current package is below
(API {manifest.get('apiVersion')}, version {entry['version']}). Bring it up to **Game API {API_VERSION}** and the
book's **unified image style**, keeping everything that already works: the learning objectives, the
flow, the wording the editor approved, and the content rules.

## What to change

1. Set `"apiVersion": "{API_VERSION}"` in both files and `"version": "{next_version}"` in game.json. Keep the
   `id` (`{gid}`) and the `chapter` ({manifest['chapter']}).
2. Use the API {API_VERSION} features where they make the activity clearer or more personal, without
   lengthening it much: personalized text (`{{{{answer:fieldId}}}}`), `ranking`, `hint`, `shuffle`,
   completion `feedback` rules, `takeaways` and `allowSaveNotes` (add the `save-notes` capability).
3. **Images:** replace the current {len(images)} image(s) with the house set: **Sheet 1**, **Sheet 2** (8
   scene images) and the **Icon**, following the image style guide below exactly. Remove old image
   assets that you no longer use from `assets`.
4. Fix anything in the current package that breaks the rules in the creation prompt below.
5. In README.md, add a "Changes in {next_version}" list.

Deliver exactly as the creation prompt says: game.json, activity.json and README.md, each in full in its
own labeled code block, then the three images labeled **Sheet 1**, **Sheet 2** and **Icon**, then a short
summary of what changed.

## The current package

{blocks}

---

{base}

---

{image_style()}

---

{api_essentials()}

---

## The chapter (approved text)

{body or "(The chapter text isn't available; keep the activity's content as it is.)"}
"""


DOCS_ORDER = ["README.md", "ai-game-creation-prompt.md", "image-style.md", "whats-new-1.1.md", "quickstart.md", "package-specification.md",
              "manifest-reference.md", "activity-schema-reference.md", "component-reference.md",
              "branching-and-state.md", "lifecycle-and-events.md", "feedback-and-scoring.md", "accessibility.md",
              "privacy-and-security.md", "validation-and-testing.md", "versioning.md"]


def docs_markdown() -> str:
    """The whole Game API documentation as one Markdown file: chat assistants can read an uploaded or
    pasted .md file, but often can't open a ZIP."""
    parts = [f"# Book Builder Game Package API {API_VERSION}: complete documentation\n\n"
             "One file containing every document, both JSON Schemas and the two template packages.\n"]
    for name in DOCS_ORDER:
        text = (DOCS / name).read_text(encoding="utf-8").strip()
        parts.append(f"\n\n---\n\n<!-- file: {name} -->\n\n" + re.sub(r"^(#+)", r"#\1", text, flags=re.M))
    for sub, label in (("schemas", "JSON Schema"), ("templates", "Template")):
        for f in sorted((DOCS / sub).rglob("*")):
            if f.is_file() and f.suffix in (".json", ".md"):
                lang = "json" if f.suffix == ".json" else "markdown"
                parts.append(f"\n\n---\n\n## {label}: `{f.relative_to(DOCS).as_posix()}`\n\n```{lang}\n"
                             f"{f.read_text(encoding='utf-8').strip()}\n```")
    return "".join(parts) + "\n"


def docs_zip() -> Path:
    out = ROOT / "dist" / f"book-builder-game-api-{API_VERSION}-docs.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(DOCS.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, f"game-developer/{p.relative_to(DOCS).as_posix()}")
    return out


def parse_reply(text: str) -> dict[str, bytes]:
    """Read game.json, activity.json and README.md out of a chat reply: each file in a fenced code block
    with its file name on a line just before it (bold, heading or plain). JSON blocks without a label
    are recognized by their contents."""
    files: dict[str, bytes] = {}
    pattern = re.compile(r"(?:^|\n)((?!```)[^\n]*)\n```[ \t]*([\w+-]*)[ \t]*\n(.*?)\n```", re.S)
    for m in pattern.finditer(text.replace("\r\n", "\n")):
        label = re.sub(r"[*#`:\s]|^file", "", m.group(1).strip(), flags=re.I).lower()
        body = m.group(3).strip() + "\n"
        name = next((n for n in ("game.json", "activity.json", "readme.md") if label.endswith(n)), None)
        if not name and m.group(2).lower() == "json":
            try:
                data = json.loads(body)
                name = "activity.json" if isinstance(data, dict) and "screens" in data else \
                    "game.json" if isinstance(data, dict) and "activityType" in data else None
            except json.JSONDecodeError:
                name = None
        if name:
            files["README.md" if name == "readme.md" else name] = body.encode("utf-8")
    missing = [n for n in ("game.json", "activity.json") if n not in files]
    if missing:
        raise PackageError(
            f"Couldn't find {' and '.join(missing)} in the pasted reply. Copy ChatGPT's whole reply (the copy "
            "button under it); each file must be in its own code block with its name on the line before it.")
    return files


def missing_assets(files: dict[str, bytes]) -> list[dict]:
    """Image (and other) assets declared in game.json that the files don't include yet."""
    try:
        manifest = json.loads(files["game.json"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    return [{"path": a.get("path"), "type": a.get("type"), "alt": a.get("alt", "")}
            for a in assets if isinstance(a, dict) and a.get("path") and a["path"] not in files]


MAX_IMAGE_WIDTH = 1600
IMAGE_TARGET_BYTES = 900_000
# Image sheets (API 1.1 house style): ChatGPT draws scene images four at a time as one high-resolution
# 2×2 sheet; the Book Manager cuts each sheet into its four images. Plus one square icon.
SHEET_PANELS = 4
SCENE_IMAGES = 8
MIN_PANEL_WIDTH = 480       # a sheet narrower than 2 × this is too small to cut into usable images
SHEET_TRIM = 0.015          # trim 1.5% from each panel edge, so seams between panels never show
ICON_SIZE = 512


def image_slots(files: dict[str, bytes]) -> list[dict]:
    """What the editor still has to choose, grouped the way ChatGPT delivers it: one slot per image
    sheet (four declared scene images, in declaration order) and one for the icon. Other missing
    assets (audio, transcripts, images beyond whole sheets) are listed one by one."""
    try:
        manifest = json.loads(files["game.json"].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    assets = [a for a in manifest.get("assets") or [] if isinstance(a, dict) and isinstance(a.get("path"), str)]
    icon = manifest.get("icon")
    scenes = [a for a in assets if a.get("type") == "image" and a["path"] != icon]
    slots, covered = [], set()
    for i in range(0, len(scenes) - len(scenes) % SHEET_PANELS, SHEET_PANELS):
        chunk = scenes[i:i + SHEET_PANELS]
        covered |= {a["path"] for a in chunk}
        if any(a["path"] not in files for a in chunk):
            n = i // SHEET_PANELS + 1
            slots.append({"slot": f"sheet-{n}", "kind": "sheet", "label": f"Sheet {n} (images {i + 1}–{i + SHEET_PANELS})",
                          "assets": [{"path": a["path"], "alt": a.get("alt", ""), "panel": j + 1} for j, a in enumerate(chunk)]})
    if isinstance(icon, str):
        covered.add(icon)
        if icon not in files:
            slots.append({"slot": "icon", "kind": "icon", "label": "Icon", "assets": [{"path": icon, "alt": "", "panel": 1}]})
    for a in assets:
        if a["path"] not in files and a["path"] not in covered:
            slots.append({"slot": a["path"], "kind": "single", "label": a["path"],
                          "assets": [{"path": a["path"], "alt": a.get("alt", ""), "panel": 1}]})
    return slots


def _open_image(data: bytes, label: str):
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415
    try:
        Image.MAX_IMAGE_PIXELS = 40_000_000
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise PackageError(f"{label}: the chosen file isn't a readable image ({e}).") from e
    return im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")


def split_sheet(data: bytes, label: str = "Sheet") -> list[bytes]:
    """Cut a 2×2 image sheet into its four panels (top-left, top-right, bottom-left, bottom-right) as PNG."""
    im = _open_image(data, label)
    if im.width < 2 * MIN_PANEL_WIDTH:
        raise PackageError(f"{label} is {im.width}×{im.height} pixels: too small to cut into four usable images. "
                           f"Ask ChatGPT for the sheet at its highest resolution (at least {2 * MIN_PANEL_WIDTH} px wide).")
    w, h = im.width // 2, im.height // 2
    dx, dy = round(w * SHEET_TRIM), round(h * SHEET_TRIM)
    panels = []
    for row in range(2):
        for col in range(2):
            out = io.BytesIO()
            im.crop((col * w + dx, row * h + dy, (col + 1) * w - dx, (row + 1) * h - dy)).save(out, "PNG")
            panels.append(out.getvalue())
    return panels


def prepare_icon(data: bytes, declared_path: str) -> bytes:
    """Centre-crop to a square and resize to the icon size, in the declared format."""
    from PIL import Image  # noqa: PLC0415
    im = _open_image(data, "Icon")
    side = min(im.size)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "PNG")
    return prepare_image(out.getvalue(), declared_path)


def prepare_image(data: bytes, declared_path: str) -> bytes:
    """Make a downloaded image fit its declared asset: same format as the declared extension, at most
    1600 px wide, re-compressed if large. Rejects files that aren't images."""
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415
    ext = PurePosixPath(declared_path).suffix.lower()
    fmt = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".gif": "GIF"}.get(ext)
    if not fmt:
        raise PackageError(f"{declared_path}: only .png, .jpg, .webp or .gif images can be attached.")
    if len(data) > 40 * 1024 * 1024:
        raise PackageError(f"{declared_path}: the chosen file is larger than 40 MB.")
    try:
        Image.MAX_IMAGE_PIXELS = 40_000_000
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise PackageError(f"{declared_path}: the chosen file isn't a readable image ({e}).") from e
    same_format = (im.format or "").upper() == fmt or (fmt == "JPEG" and im.format == "MPO")
    if same_format and im.width <= MAX_IMAGE_WIDTH and len(data) <= IMAGE_TARGET_BYTES:
        return data
    if im.width > MAX_IMAGE_WIDTH:
        im = im.resize((MAX_IMAGE_WIDTH, round(im.height * MAX_IMAGE_WIDTH / im.width)), Image.LANCZOS)
    if fmt == "JPEG" and im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    out = io.BytesIO()
    for quality in (86, 80, 72, 64):
        out = io.BytesIO()
        kwargs = {"optimize": True}
        if fmt in ("JPEG", "WEBP"):
            kwargs["quality"] = quality
        im.save(out, fmt, **kwargs)  # also drops metadata such as EXIF location
        if fmt in ("PNG", "GIF") or out.tell() <= IMAGE_TARGET_BYTES:
            break
    if fmt == "PNG" and out.tell() > 2 * IMAGE_TARGET_BYTES and im.mode in ("RGB", "RGBA"):
        out = io.BytesIO()
        im.quantize(colors=256).save(out, "PNG", optimize=True)  # large photo-like PNGs
    return out.getvalue()


def attach_assets(files: dict[str, bytes], uploads: dict[str, bytes]) -> dict[str, bytes]:
    """Add chosen files. Keys are slots from image_slots() ("sheet-1", "sheet-2", "icon") or declared
    asset paths. Sheets are cut into their four images; every image is prepared to match its name."""
    import jobs as J
    declared = {a["path"]: a for a in missing_assets(files)}
    slots = {s["slot"]: s for s in image_slots(files)}
    out = dict(files)
    for i, (key, data) in enumerate(uploads.items()):
        slot = slots.get(key)
        J.report(0.1 + 0.5 * i / max(1, len(uploads)), f"Preparing {slot['label'] if slot else key}…")
        if slot and slot["kind"] == "sheet":
            for a, panel in zip(slot["assets"], split_sheet(data, slot["label"])):
                out[a["path"]] = prepare_image(panel, a["path"])
        elif slot and slot["kind"] == "icon":
            out[slot["assets"][0]["path"]] = prepare_icon(data, slot["assets"][0]["path"])
        elif key in declared:
            out[key] = prepare_image(data, key) if declared[key]["type"] == "image" else data
        else:
            raise PackageError(f"{key} isn't a missing asset declared in game.json.")
    return out


def zip_files(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ------------------------------------------------------------------ cli

def main() -> None:
    ap = argparse.ArgumentParser(description="Book Builder Game Package Manager")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("validate"); s.add_argument("zip")
    s = sub.add_parser("import"); s.add_argument("zip"); s.add_argument("--replace", action="store_true")
    sub.add_parser("list")
    for name in ("show", "approve", "unapprove", "reject", "remove"):
        s = sub.add_parser(name); s.add_argument("id")
    s = sub.add_parser("assign"); s.add_argument("id"); s.add_argument("chapter", type=int)
    s = sub.add_parser("export"); s.add_argument("id"); s.add_argument("--out")
    s = sub.add_parser("prompt"); s.add_argument("chapter", type=int, nargs="?")
    sub.add_parser("docs-zip")
    s = sub.add_parser("docs-md"); s.add_argument("--out")
    s = sub.add_parser("import-reply"); s.add_argument("file"); s.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    try:
        if a.cmd == "validate":
            res = validate_package(read_archive(Path(a.zip).read_bytes()))
            for e in res["errors"]:
                print(f"ERROR   {e}")
            for w in res["warnings"]:
                print(f"WARNING {w}")
            print("valid" if res["ok"] else "INVALID")
            sys.exit(0 if res["ok"] else 1)
        if a.cmd == "import":
            res = install(Path(a.zip).read_bytes(), replace=a.replace, source=Path(a.zip).name)
            e = res["entry"]
            print(f"{'updated' if res['replaced'] else 'installed'} {e['id']} {e['version']} for chapter {e['chapter']}"
                  " (status: review; approve it after previewing)")
            for w in res["warnings"]:
                print(f"WARNING {w}")
        elif a.cmd == "list":
            games = load_registry()["games"].values()
            if not games:
                print("No games installed.")
            for g in sorted(games, key=lambda g: (g["chapter"], g["id"])):
                print(f"ch{g['chapter']:>2}  {g['status']:<9} {g['id']:<32} {g['version']:<8} {g['title']}")
        elif a.cmd == "show":
            print(json.dumps(get(a.id), indent=2))
        elif a.cmd in ("approve", "unapprove", "reject"):
            g = set_status(a.id, {"approve": "approved", "unapprove": "review", "reject": "rejected"}[a.cmd])
            print(f"{g['id']}: {g['status']}")
        elif a.cmd == "assign":
            g = assign(a.id, a.chapter)
            print(f"{g['id']} now belongs to chapter {g['chapter']} (status reset to review)")
        elif a.cmd == "remove":
            remove(a.id)
            print(f"removed {a.id}")
        elif a.cmd == "export":
            print(export(a.id, Path(a.out) if a.out else None))
        elif a.cmd == "prompt":
            print(creation_prompt(a.chapter))
        elif a.cmd == "docs-zip":
            print(docs_zip())
        elif a.cmd == "docs-md":
            out = Path(a.out or ROOT / "dist" / f"book-builder-game-api-{API_VERSION}.md")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(docs_markdown(), encoding="utf-8")
            print(out)
        elif a.cmd == "import-reply":
            files = parse_reply(Path(a.file).read_text(encoding="utf-8"))
            res = install(zip_files(files), replace=a.replace, source=Path(a.file).name)
            print(f"installed {res['entry']['id']} {res['entry']['version']} (status: review)")
            for w in res["warnings"]:
                print(f"WARNING {w}")
    except PackageError as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    main()
