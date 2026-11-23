"""Images in chapters: resolve, check and stage them for every output format.

Rules (shared by tools/build.py and tools/website.py):
- `![alt](path)` and `<img src="path">` are resolved against the chapter's own folder first, then the
  book folder, and normalised to a book-relative path. The result must stay inside the book.
- Remote (http/https), data:, file: and absolute paths, private folders (sources-private, research,
  drafts, …) and missing files are never used: the image is replaced by a visible "[Image: alt]" note
  and a warning, so nothing disappears silently.
- Images from the Image Studio (images/…) must be approved to be published; book builds of drafts keep
  them but warn.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

MD_IMG = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?P<title>\s+"[^"]*")?\)(?P<attrs>\{[^}]*\})?')
HTML_IMG = re.compile(r'<img\b[^>]*?\bsrc="(?P<src>[^"]+)"[^>]*>', re.I)
BLOCKED_DIRS = ("sources-private", "research", "drafts", "reviews", "prompts", "briefs", "dist", ".git", ".publish",
                "research-library", "sources-inbox")
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _approved_images(root: Path) -> set[str]:
    try:
        reg = json.loads((root / "images" / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {v["path"] for r in reg.get("images", []) if r.get("status") == "approved" for v in r.get("versions", [])[-1:]}


def check_path(src: str, chapter: Path, root: Path) -> tuple[str | None, str]:
    """(book-relative path, problem). Exactly one of the two is set."""
    s = src.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*:", s, re.I):
        return None, "remote or inline images aren't used in book outputs (download the image into the book first)"
    if s.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", s):
        return None, "absolute paths aren't allowed; use a path inside the book"
    root = root.resolve()
    for base in (chapter.parent, root):
        cand = (base / s).resolve()
        if not cand.is_relative_to(root):
            return None, "the path leads outside the book"
        if cand.is_file():
            rel = cand.relative_to(root).as_posix()
            if rel.split("/")[0] in BLOCKED_DIRS:
                return None, f"images can't come from {rel.split('/')[0]}/ (private or working folder)"
            if cand.suffix.lower() not in ALLOWED_EXT:
                return None, f"{cand.suffix or 'this'} isn't an image type the outputs support"
            return rel, ""
    return None, "the file doesn't exist"


def resolve(body: str, chapter: Path, root: Path, published: bool = False) -> tuple[str, list[str], list[str]]:
    """Rewrite image paths in one chapter's Markdown. Returns (body, book-relative image paths, warnings)."""
    approved = _approved_images(root)
    found, warns = [], []
    label = chapter.name

    def fix(m: re.Match) -> str:
        alt, src = m.group("alt").strip(), m.group("src")
        rel, problem = check_path(src, chapter, root)
        if rel and rel.startswith("images/") and rel not in approved:
            if published:
                problem = "it isn't approved in the Image Studio"
            else:
                warns.append(f"{label}: {src} isn't approved in the Image Studio yet (kept in this draft build)")
        if problem:
            warns.append(f"{label}: image “{alt or src}” left out: {problem}")
            return f"*[Image: {alt or Path(src).name}]*"
        found.append(rel)
        return f"![{m.group('alt')}]({rel}{m.group('title') or ''}){m.group('attrs') or ''}"

    def fix_html(m: re.Match) -> str:
        src = m.group("src")
        rel, problem = check_path(src, chapter, root)
        if rel and rel.startswith("images/") and rel not in approved and published:
            problem = "it isn't approved in the Image Studio"
        if problem:
            alt = re.search(r'\balt="([^"]*)"', m.group(0))
            warns.append(f"{label}: image “{src}” left out: {problem}")
            return f"<em>[Image: {(alt.group(1) if alt else Path(src).name)}]</em>"
        found.append(rel)
        return m.group(0).replace(f'src="{src}"', f'src="{rel}"')

    body = MD_IMG.sub(fix, body)
    body = HTML_IMG.sub(fix_html, body)
    return body, found, warns


def publish(html: str, root: Path, public: Path, base: str) -> tuple[str, list[str]]:
    """Website: copy each referenced book image into public/book-media/ and point the HTML at it."""
    copied = []

    def swap(m: re.Match) -> str:
        src = m.group(1)
        if re.match(r"^[a-z][a-z0-9+.-]*:|^/|^#", src, re.I):
            return m.group(0)
        f = (root / src).resolve()
        if not f.is_relative_to(root.resolve()) or not f.is_file():
            return m.group(0)
        digest = hashlib.sha256(f.read_bytes()).hexdigest()[:10]
        name = f"{digest}-{f.name}"
        dest = public / "book-media" / name
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        copied.append(name)
        return f'src="{base.rstrip("/")}/book-media/{name}"'

    return re.sub(r'src="([^"]+)"', swap, html), copied
