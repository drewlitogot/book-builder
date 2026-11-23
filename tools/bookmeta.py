"""Book Details: read and save book.yml metadata without disturbing the rest of the file.

Owned by the Book Management module (see MODULES.json). Used by the web app's /api/book/save route
and by api_library. Saving rewrites only changed lines; comments, chapter order and other keys stay.
"""
from __future__ import annotations

import json
import re

import chapter as C

ROOT = C.ROOT


# Book Details: book.yml metadata, saved back line by line so the file's comments, chapter list and
# any other keys stay exactly as they are. Keys follow pandoc's metadata names where one exists
# (description, abstract, subject, keywords, identifier), so EPUB and HTML pick them up.
BOOK_FIELDS = ("title", "subtitle", "author", "publisher", "editor", "credit-line", "author-bio", "about-authors", "description", "synopsis", "subject",
               "intended-audience", "lang", "keywords", "rights", "date", "publication-date",
               "papersize", "fontsize", "identifier",
               "margin.inside", "margin.outside", "margin.top", "margin.bottom")


def book_meta() -> dict:
    import yaml  # noqa: PLC0415
    meta = (yaml.safe_load((ROOT / "book.yml").read_text(encoding="utf-8")) or {}).get("metadata", {}) or {}
    out = {}
    for k in BOOK_FIELDS:
        v = (meta.get("margin") or {}).get(k.split(".")[1]) if k.startswith("margin.") else meta.get(k)
        out[k] = ", ".join(map(str, v)) if isinstance(v, list) else "" if v is None else str(v)
    return out


def _yaml_scalar(key: str, value: str) -> str:
    import yaml  # noqa: PLC0415
    if key == "keywords":
        items = [w.strip() for w in value.split(",") if w.strip()]
        return yaml.safe_dump(items, default_flow_style=True, allow_unicode=True, width=10000).strip()
    if "\n" in value:
        return json.dumps(value, ensure_ascii=False)         # one line, YAML-compatible double quotes
    return yaml.safe_dump(value, allow_unicode=True, width=10000).strip().removesuffix("...").strip()


REQUIRED_META = {"title", "author"}


def save_book_meta(data: dict) -> dict:
    import yaml  # noqa: PLC0415
    path = ROOT / "book.yml"
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed, current = [], book_meta()
    # where the metadata block ends (first top-level key after "metadata:")
    try:
        meta_start = next(i for i, ln in enumerate(lines) if ln.startswith("metadata:"))
    except StopIteration:
        return {"ok": False, "message": "book.yml has no metadata section."}
    meta_end = next((i for i in range(meta_start + 1, len(lines)) if re.match(r"^[A-Za-z]", lines[i])), len(lines))
    for key in BOOK_FIELDS:
        if key not in data:
            continue
        raw = str(data[key]).replace("\r", "")
        value = raw.strip() if key in ("description", "synopsis", "author-bio", "about-authors") else " ".join(raw.split())
        if value == current[key]:
            continue
        if not value and key in REQUIRED_META:
            return {"ok": False, "message": f"{key.capitalize()} can't be empty."}
        if key.startswith("margin."):
            sub = key.split(".")[1]
            mi = next((i for i in range(meta_start, meta_end) if lines[i].startswith("  margin:")), None)
            idx = next((i for i in range(mi + 1, meta_end) if mi is not None and re.match(rf"^    {sub}:", lines[i])), None) \
                if mi is not None else None
            if idx is None or not value:
                continue
            lines[idx] = f"    {sub}: {_yaml_scalar(key, value)}\n"
            changed.append(key)
            continue
        idx = next((i for i in range(meta_start + 1, meta_end) if re.match(rf"^  {re.escape(key)}:", lines[i])), None)
        if not value:                       # clearing an optional field removes its line
            if idx is not None:
                del lines[idx]
                meta_end -= 1
                changed.append(key)
            continue
        new = f"  {key}: {_yaml_scalar(key, value)}\n"
        if idx is None:
            lines.insert(meta_end, new)
            meta_end += 1
        else:
            lines[idx] = new
        changed.append(key)
    if not changed:
        return {"ok": True, "message": "Nothing changed.", "book": book_meta()}
    text = "".join(lines)
    before = yaml.safe_load(original) or {}
    after = yaml.safe_load(text) or {}   # refuse to write a file that no longer parses
    if after.get("parts") != before.get("parts"):
        return {"ok": False, "message": "Refused: saving would have changed the chapter list."}
    path.write_text(text, encoding="utf-8")
    return {"ok": True, "message": f"Saved {', '.join(changed)} in book.yml.", "book": book_meta()}


