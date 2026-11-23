#!/usr/bin/env python3
"""Build a book from Markdown.

Usage:
    python tools/build.py build [pdf|epub|html|docx|all ...]   (default: pdf)
    python tools/build.py check
    python tools/build.py status

Options for build:
    --only-perspective men|women|nonbinary   keep only that perspective's callouts
    --only-neurotype GROUP                    keep only that reader group's callouts

Requires Pandoc 3.x, Typst (for PDF) and PyYAML (pip install -r requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Run: pip install -r requirements.txt")

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
MANIFEST = ROOT / "book.yml"
BOOK_DIR = ROOT / "book"
DIST = ROOT / "dist"
WORK = DIST / ".work"
BIB = ROOT / "references.bib"
CSL = ROOT / "assets/csl/apa.csl"
FILTER = ROOT / "assets/filters/callouts.lua"
TYPST_HEADER = ROOT / "assets/typst/callouts.typ"
CSS = ROOT / "assets/css/book.css"
BRAND_CSS = ROOT / "assets/css/brand.css"   # written by Design › Brand Kit (tools/brand.py); optional


def brand_css_args() -> list[str]:
    """The book's applied brand loads after book.css, so it overrides it; absent = unchanged output."""
    return ["--css", str(BRAND_CSS)] if BRAND_CSS.exists() else []


def brand_font_files() -> list[Path]:
    """Font files the applied brand uses, for embedding in the EPUB."""
    if not BRAND_CSS.exists():
        return []
    import re as _re  # noqa: PLC0415
    names = set(_re.findall(r'url\("\.\./fonts/([^"]+)"\)', BRAND_CSS.read_text(encoding="utf-8")))
    return [FONTS / n for n in sorted(names) if (FONTS / n).exists()]
TYPST_FRONT = ROOT / "assets/typst/front.typ"
COVER = ROOT / "assets/branding/cover.jpg"
LOGO = ROOT / "assets/branding/logo-black.png"
FONTS = ROOT / "assets/fonts"
# Fonts embedded in the EPUB: Source Serif 4 for reading, Playfair Display for titles.
EPUB_FONTS = ["SourceSerif4.ttf", "SourceSerif4-Italic.ttf", "PlayfairDisplay.ttf", "PlayfairDisplay-Italic.ttf",
              "SourceSans3.ttf"]
def _output_stem() -> str:
    """Output file names follow the book's title ("My Book" -> my-book.pdf)."""
    import re as _re  # noqa: PLC0415
    try:
        m = _re.search(r"^\s*title:\s*['\"]?(.+?)['\"]?\s*$", (ROOT / "book.yml").read_text(encoding="utf-8"), _re.M)
        stem = _re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-") if m else ""
    except OSError:
        stem = ""
    return stem[:60] or "book"


OUTPUT_STEM = _output_stem()
# Set by --published (only approved chapters) and --outdir.
PUBLISHED_ONLY = False
OUTDIR = DIST
# PDF contents and navigation (Build view settings). "simple": parts and chapter titles only;
# "detailed": section headings too. Bookmarks always list every heading level when enabled.
TOC_MODE = "simple"
PDF_BOOKMARKS = True
TOC_LINKS = True

FORMATS = ("pdf", "epub", "html", "docx")
STATUSES = ("planned", "brief", "draft", "factchecked", "reviewed",
            "approved", "human-reviewed", "generated")
CALLOUT_VALUES = {
    "perspective": {"men", "women", "nonbinary"},
    "neurotype": {"group-a", "group-b"},
}
CALLOUT_VALUES["partner"] = CALLOUT_VALUES["neurotype"]

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", re.S)
CITE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
BIB_KEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,")
CALLOUT_RE = re.compile(r"^:::+\s*\{\.(perspective|neurotype|partner)\s+for=\"([^\"]*)\"([^}]*)\}", re.M)
NEEDS_SOURCE = "[NEEDS SOURCE]"


@dataclass
class Chapter:
    path: Path
    part: str
    meta: dict = field(default_factory=dict)
    body: str = ""

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()

    @property
    def words(self) -> int:
        return len(re.findall(r"\b\w+\b", self.body))


# ---------------------------------------------------------------- loading

def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"Missing {MANIFEST.name}")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}


def split_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    return (yaml.safe_load(m.group(1)) or {}), text[m.end():]


def load_chapters(manifest: dict) -> tuple[list[Chapter], list[str]]:
    chapters, missing = [], []
    for part in manifest.get("parts", []):
        for rel in part.get("chapters", []):
            path = ROOT / rel
            if not path.exists():
                missing.append(rel)
                continue
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            chapters.append(Chapter(path, part.get("title", ""), meta, body))
    return chapters, missing


def bib_keys() -> set[str]:
    if not BIB.exists():
        return set()
    return set(BIB_KEY_RE.findall(BIB.read_text(encoding="utf-8")))


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`]*`", "", text)


# ---------------------------------------------------------------- check

def run_check(manifest: dict, quiet: bool = False) -> bool:
    errors: list[str] = []
    warnings: list[str] = []

    chapters, missing = load_chapters(manifest)
    for rel in missing:
        errors.append(f"listed in book.yml but missing: {rel}")

    listed = {c.path for c in chapters}
    for path in sorted(BOOK_DIR.rglob("*.md")):
        if path not in listed:
            errors.append(f"not listed in book.yml: {path.relative_to(ROOT)}")

    keys = bib_keys()
    for ch in chapters:
        body = strip_code(ch.body)
        status = ch.meta.get("status")
        if status not in STATUSES:
            warnings.append(f"{ch.rel}: unknown status {status!r}")

        for key in sorted(set(CITE_RE.findall(body))):
            if key not in keys:
                errors.append(f"{ch.rel}: citation @{key} not in references.bib")

        for kind, value, rest in CALLOUT_RE.findall(body):
            if value not in CALLOUT_VALUES[kind]:
                errors.append(f"{ch.rel}: unknown {kind} value {value!r}")
            if kind in ("neurotype", "partner") and "title=" not in rest:
                warnings.append(f"{ch.rel}: {kind} box ({value}) needs an experience-based title=\"...\"")

        n = ch.body.count(NEEDS_SOURCE)
        if n:
            warnings.append(f"{ch.rel}: {n} × {NEEDS_SOURCE}")

    for label, items in (("ERROR", errors), ("warning", warnings)):
        for item in items:
            print(f"{label}: {item}")
    if not quiet or errors:
        print(f"check: {len(chapters)} chapters, {len(errors)} errors, "
              f"{len(warnings)} warnings")
    return not errors


# ---------------------------------------------------------------- status

def run_status(manifest: dict) -> None:
    chapters, missing = load_chapters(manifest)
    rows = [(c.rel, str(c.meta.get("status", "?")), str(c.words),
             str(c.body.count(NEEDS_SOURCE))) for c in chapters]
    rows += [(rel, "MISSING", "-", "-") for rel in missing]
    header = ("chapter", "status", "words", "needs source")
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(4)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))
    total = sum(c.words for c in chapters)
    print(f"\n{len(chapters)} chapters, {total:,} words")


# ---------------------------------------------------------------- build

PREFLIGHT: list[str] = []   # warnings found while assembling the book (missing or refused images, …)


def record_artifact(out: Path, fmt: str) -> None:
    """dist/build-manifest.json: what was built, when, its checksum, the book's id and the preflight warnings."""
    import hashlib  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    import time as _time  # noqa: PLC0415
    try:
        import registry as REG  # noqa: PLC0415
        pid = REG.project_file(ROOT).get("project_id") or REG.ensure(ROOT).get("id")
    except Exception:  # noqa: BLE001
        pid = None
    mf = OUTDIR / "build-manifest.json"
    try:
        data = _json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"schema": 1, "artifacts": {}}
    data["artifacts"][out.name] = {
        "file": out.name, "format": fmt, "bytes": out.stat().st_size,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "built": _time.time(), "project_id": pid,
        "published_only": PUBLISHED_ONLY, "toc": TOC_MODE, "preflight": list(PREFLIGHT)}
    mf.write_text(_json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def combine(manifest: dict) -> Path:
    """Concatenate chapters into one Markdown file, dropping per-chapter front matter."""
    chapters, missing = load_chapters(manifest)
    if missing:
        sys.exit("Missing chapters; run `check` for details.")
    WORK.mkdir(parents=True, exist_ok=True)

    if PUBLISHED_ONLY:
        chapters = [c for c in chapters if c.meta.get("status") in ("approved", "generated")]
    activities = activity_blocks()

    import media  # noqa: PLC0415  (images: resolve per chapter, keep inside the book, warn instead of dropping)
    out: list[str] = []
    current_part = None
    PREFLIGHT.clear()
    for ch in chapters:
        if ch.part != current_part:
            current_part = ch.part
            out.append(f"\n# {ch.part} {{.part .unnumbered}}\n")
        out.append(f"\n<!-- source: {ch.rel} -->\n")
        body, _imgs, warns = media.resolve(ch.body, ch.path, ROOT, published=PUBLISHED_ONLY)
        PREFLIGHT.extend(warns)
        out.append(body.strip() + "\n")
        m = re.match(r"^(\d+)-", ch.path.name)
        if m and "00-front" not in ch.rel and int(m.group(1)) in activities:
            out.append(activities[int(m.group(1))])

    combined = WORK / "book.md"
    combined.write_text("\n".join(out), encoding="utf-8")

    meta = dict(manifest.get("metadata", {}))
    meta.setdefault("link-citations", True)
    # PDF (Typst) page setup; ignored by other formats. Defaults to a 6x9in US
    # trade paperback rather than Letter, with asymmetric margins so the inside
    # edge clears the binding. Override in book.yml metadata.
    meta.setdefault("papersize", "us-trade")
    meta.setdefault("margin", {"inside": "0.875in", "outside": "0.625in",
                               "top": "0.75in", "bottom": "0.75in"})
    meta.setdefault("fontsize", "11pt")
    (WORK / "metadata.yml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # The PDF draws its own cover and title page (assets/typst/front.typ), so
    # Pandoc's plain title block is left out of the PDF's metadata.
    pdf_meta = {k: v for k, v in meta.items() if k not in ("title", "subtitle", "author", "date")}
    (WORK / "metadata-pdf.yml").write_text(
        yaml.safe_dump(pdf_meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    esc = lambda v: (str(v or "").replace("\\", "").replace("[", "(").replace("]", ")").replace("#", "")
                     .replace("*", "").replace("_", " ").replace("$", "").replace("@", "(at)").replace("<", "‹"))
    front = TYPST_FRONT.read_text(encoding="utf-8")
    front = (front.replace("COVER_PATH", COVER.as_posix()).replace("LOGO_PATH", LOGO.as_posix())
             .replace("TITLE_LOWER", esc(meta.get("title")).lower())
             .replace("SUBTITLE", esc(meta.get("subtitle")).lower())
             .replace("RIGHTS", esc(meta.get("rights")))
             .replace("CREATED_BY", f"Created by {esc(meta.get('editor'))}" if meta.get("editor") else "")
             .replace("CREDIT_LINE", esc(meta.get("credit-line")))
             .replace("ABOUT_AUTHORS", esc(meta.get("about-authors")))
             .replace("AUTHOR", esc(meta.get("author"))))
    if not meta.get("about-authors"):        # no credits statement: rights stay on the title page
        front = re.sub(r"// ABOUT-START.*?// ABOUT-END\n", "", front, flags=re.S).replace(
            "  // CREDITS-END\n", f"  // CREDITS-END\n  #v(1em)\n  #text(font: ui-font, size: 8.5pt, fill: charcoal)[{esc(meta.get('rights'))}]\n")
    (WORK / "front.typ").write_text(front, encoding="utf-8")

    # The Typst header needs the book title for the running heads, so it is
    # written out with the title bound rather than hardcoded in the asset.
    title = str(meta.get("title", "")).replace("\\", "").replace('"', "'")
    (WORK / "header.typ").write_text(
        f'#let book-title = "{title}"\n'
        f'#let pdf-bookmarks = {str(PDF_BOOKMARKS).lower()}\n'
        f'#let toc-links = {str(TOC_LINKS).lower()}\n\n'
        + TYPST_HEADER.read_text(encoding="utf-8"), encoding="utf-8")
    return combined


def activity_blocks() -> dict[int, str]:
    """Short "Interactive activity" notes, with a link and QR code, for chapters with published games.

    The book stays complete without them; they only point readers to the website version.
    """
    site = ROOT / "website.yml"
    if not site.exists():
        return {}
    url = (yaml.safe_load(site.read_text(encoding="utf-8")) or {}).get("url")
    if not url:
        return {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import games  # noqa: PLC0415
        published = games.published_games()
    except Exception as e:  # noqa: BLE001
        print(f"  (activity notes skipped: {e})", file=sys.stderr)
        return {}
    try:
        import segno  # noqa: PLC0415
    except ImportError:
        segno = None
    blocks: dict[int, list[str]] = {}
    for g in published:
        manifest = json.loads((ROOT / "games" / "packages" / g["id"] / "game.json").read_text(encoding="utf-8"))
        link = f"{url.rstrip('/')}/activities/{g['id']}/"
        text = (f"::: {{.activity}}\n**Interactive activity: {manifest['title']}.** {manifest['description']} "
                f"It's optional and works in any web browser: <{link}>\n")
        if segno:
            qr = WORK / "qr" / f"{g['id']}.png"
            qr.parent.mkdir(parents=True, exist_ok=True)
            segno.make(link, error="m").save(str(qr), scale=6, border=2)
            text += f"\n![QR code for the activity at {link}]({qr}){{width=0.9in}}\n"
        blocks.setdefault(g["chapter"], []).append(text + ":::\n")
    return {n: "\n".join(b) for n, b in blocks.items()}


def pandoc_cmd(fmt: str, combined: Path, out: Path, extra_meta: dict) -> list[str]:
    cmd = [
        "pandoc", str(combined),
        "--from", "markdown",
        "--metadata-file", str(WORK / ("metadata-pdf.yml" if fmt == "pdf" else "metadata.yml")),
        "--lua-filter", str(FILTER),
        # books without a bibliography (fiction, children's) build without citation processing
        *(["--citeproc", "--bibliography", str(BIB), "--csl", str(CSL)] if BIB.exists() else []),
        "--resource-path", f"{ROOT}:{BOOK_DIR}",
        "--toc", f"--toc-depth={1 if fmt == 'pdf' and TOC_MODE == 'simple' else 2}",
        "--output", str(out),
    ]
    for k, v in extra_meta.items():
        cmd += ["--metadata", f"{k}={v}"]

    if fmt == "pdf":
        cmd += ["--pdf-engine", "typst",
                "--pdf-engine-opt=--root=/",
                f"--pdf-engine-opt=--font-path={FONTS}",
                "--include-in-header", str(WORK / "header.typ")]
        if COVER.exists():
            cmd += ["--include-before-body", str(WORK / "front.typ")]
    elif fmt == "epub":
        cmd += ["--to", "epub3", "--css", str(CSS), *brand_css_args(), "--split-level=1"]
        if COVER.exists():
            cmd += ["--epub-cover-image", str(COVER)]
        cmd += [f"--epub-embed-font={FONTS / f}" for f in EPUB_FONTS if (FONTS / f).exists()]
        cmd += [f"--epub-embed-font={p}" for p in brand_font_files() if p.name not in EPUB_FONTS]
    elif fmt == "html":
        cmd += ["--to", "html5", "--standalone", "--embed-resources",
                "--css", str(CSS), *brand_css_args()]
    elif fmt == "docx":
        cmd += ["--to", "docx"]
    return cmd


def require(tool: str, hint: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"`{tool}` not found. {hint}")


def run_build(manifest: dict, formats: list[str], extra_meta: dict) -> None:
    require("pandoc", "Install with: brew install pandoc")
    if "pdf" in formats:
        require("typst", "Install with: brew install typst")

    import jobs as J
    J.report(0.02, "Checking the chapters…")
    if not run_check(manifest, quiet=True):
        sys.exit("Build stopped: fix the errors above first.")

    combined = combine(manifest)
    for w in PREFLIGHT:
        print(f"  ! {w}", file=sys.stderr)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stem = OUTPUT_STEM
    for key, value in extra_meta.items():
        stem += f"-{value}"

    ok = True
    # Rough share of the time each format takes (the PDF is the slow one).
    weight = {"pdf": 5, "epub": 2, "docx": 1, "html": 1}
    seconds = {"pdf": 40, "epub": 12, "docx": 6, "html": 6}  # typical, on a laptop
    total = sum(weight.get(f, 1) for f in formats)
    done = 0
    for fmt in formats:
        a = 0.05 + 0.95 * done / total
        done += weight.get(fmt, 1)
        out = OUTDIR / f"{stem}.{fmt}"
        with J.creep(a, 0.05 + 0.95 * done / total, seconds.get(fmt, 10), f"Building the {fmt.upper()}…"):
            result = subprocess.run(pandoc_cmd(fmt, combined, out, extra_meta),
                                    cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            ok = False
            print(f"✗ {fmt}: pandoc failed\n{result.stderr}", file=sys.stderr)
            continue
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        print(f"✓ {fmt}: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
        record_artifact(out, fmt)

        if fmt == "epub" and shutil.which("epubcheck"):
            check = subprocess.run(["epubcheck", str(out)],
                                   capture_output=True, text=True)
            status = "valid" if check.returncode == 0 else "INVALID"
            print(f"  epubcheck: {status}")
            if check.returncode != 0:
                print(check.stdout[-2000:], file=sys.stderr)
    J.report(1.0, "Done")
    if not ok:
        sys.exit(1)


# ---------------------------------------------------------------- cli

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    b = sub.add_parser("build", help="build output formats into dist/")
    b.add_argument("formats", nargs="*", default=["pdf"],
                   choices=[*FORMATS, "all"], metavar="FORMAT",
                   help="pdf, epub, html, docx or all (default: pdf)")
    b.add_argument("--only-perspective", choices=sorted(CALLOUT_VALUES["perspective"]))
    b.add_argument("--only-neurotype", choices=sorted(CALLOUT_VALUES["neurotype"]))
    b.add_argument("--published", action="store_true",
                   help="only approved chapters (what the website publishes)")
    b.add_argument("--outdir", help="write the files here instead of dist/")
    b.add_argument("--toc", choices=["simple", "detailed"], default="simple",
                   help="PDF contents: chapter titles only (default) or with section headings")
    b.add_argument("--no-bookmarks", action="store_true", help="leave PDF bookmarks out")
    b.add_argument("--no-toc-links", action="store_true", help="make PDF contents entries plain text")

    sub.add_parser("check", help="validate the manifest, citations and callouts")
    sub.add_parser("status", help="show each chapter's pipeline status")

    args = parser.parse_args()
    manifest = load_manifest()

    if args.command == "check":
        sys.exit(0 if run_check(manifest) else 1)
    elif args.command == "status":
        run_status(manifest)
    elif args.command == "build":
        global PUBLISHED_ONLY, OUTDIR, TOC_MODE, PDF_BOOKMARKS, TOC_LINKS
        PUBLISHED_ONLY = args.published
        TOC_MODE, PDF_BOOKMARKS, TOC_LINKS = args.toc, not args.no_bookmarks, not args.no_toc_links
        if args.outdir:
            OUTDIR = Path(args.outdir).resolve()
        formats = list(FORMATS) if "all" in args.formats else list(dict.fromkeys(args.formats))
        extra = {}
        if args.only_perspective:
            extra["only-perspective"] = args.only_perspective
        if args.only_neurotype:
            extra["only-neurotype"] = args.only_neurotype
        run_build(manifest, formats, extra)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
