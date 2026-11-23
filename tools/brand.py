"""Brand Studio: one set of design tokens per book (brand.json), applied to the book's outputs.

brand.json lives in the book's folder. It never styles the Book Builder interface. Applying it writes:
  - PDF:       font and color `#let` lines in assets/typst/callouts.typ (insights.set_typst_brand)
  - EPUB/HTML: assets/css/brand.css (loaded after book.css by tools/build.py; fonts embedded in EPUB)
  - Website:   site/src/generated/brand.css (written by tools/website.py export, loaded after global.css)
A book without brand.json keeps its outputs exactly as they were.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import chapter as C
import insights as I

ROOT = C.ROOT
FILE = ROOT / "brand.json"
BRAND_CSS = ROOT / "assets" / "css" / "brand.css"
FONTS_DIR = ROOT / "assets" / "fonts"
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Token -> (PDF template color name, CSS custom properties). Names follow the book template.
COLOR_TOKENS = {
    "ink": ("ink", ["--ink"], "Body text"),
    "paper": ("paper", ["--paper"], "Page background"),
    "accent": ("teal", ["--teal"], "Main accent (links, callouts)"),
    "highlight": ("mustard", ["--mustard"], "Highlight (logo underline, key callouts)"),
    "secondary": ("violet", ["--violet"], "Secondary accent"),
    "text2": ("charcoal", ["--charcoal"], "Secondary text (captions, headers)"),
    "rule": ("soft-gray", ["--soft-gray", "--line"], "Rules and borders"),
}
FONT_TOKENS = {"display": "Titles and headings", "body": "Body text", "ui": "Captions, callouts, running heads"}
ASSET_SLOTS = {"logo": "Logo", "favicon": "Icon / favicon", "cover": "Front cover"}
ASSET_TYPES = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg", b"RIFF": ".webp"}


# ------------------------------------------------------------------ colors
def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexv: str) -> float:
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def darken_to(fg: str, bg: str, target: float = 4.5) -> str:
    """Darken (or lighten on dark paper) fg until it reaches `target` contrast on bg."""
    r, g, b = (int(fg[i:i + 2], 16) for i in (1, 3, 5))
    step = -1 if luminance(bg) > 0.4 else 1
    for _ in range(256):
        if contrast(f"#{r:02X}{g:02X}{b:02X}", bg) >= target:
            break
        r, g, b = (max(0, min(255, v + step * 4)) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def checks(colors: dict) -> list[dict]:
    """WCAG contrast for the pairs readers actually see."""
    out = []
    pairs = [("ink", "paper", 7.0, "Body text on the page"), ("text2", "paper", 4.5, "Secondary text on the page"),
             ("accent", "paper", 4.5, "Accent used as link or text"), ("ink", "highlight", 4.5, "Text on highlight")]
    for fg, bg, need, what in pairs:
        if colors.get(fg) and colors.get(bg):
            ratio = contrast(colors[fg], colors[bg])
            status = "pass" if ratio >= need else "warn" if ratio >= 3 else "fail"
            out.append({"pair": f"{fg} on {bg}", "what": what, "ratio": ratio, "needed": need, "status": status})
    return out


# ------------------------------------------------------------------ load / save
def defaults() -> dict:
    """The book's current look, read from its PDF template, so saving defaults changes nothing."""
    t = I.typst_brand()
    colors = {k: t["colors"].get(v[0]) for k, v in COLOR_TOKENS.items() if t["colors"].get(v[0])}
    fonts = {k: t["fonts"].get(k) for k in FONT_TOKENS if t["fonts"].get(k)}
    return {"schema": 1, "vibe": "", "voice": {"tone": "", "person": "", "readingLevel": "", "avoid": ""},
            "colors": colors, "fonts": fonts, "imagery": "", "assets": {}}


def load() -> dict:
    base = defaults()
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**base, "saved": False}
    for k in ("vibe", "imagery"):
        base[k] = str(saved.get(k, base[k]))[:2000]
    base["voice"].update({k: str(v)[:500] for k, v in (saved.get("voice") or {}).items() if k in base["voice"]})
    base["colors"].update({k: v.upper() for k, v in (saved.get("colors") or {}).items() if k in COLOR_TOKENS and HEX.match(str(v))})
    base["fonts"].update({k: v for k, v in (saved.get("fonts") or {}).items() if k in FONT_TOKENS and re.fullmatch(r"[A-Za-z0-9 ]{2,60}", str(v))})
    base["assets"] = {k: v for k, v in (saved.get("assets") or {}).items() if k in ASSET_SLOTS and isinstance(v, str)}
    return {**base, "saved": True, "applied": saved.get("applied")}


def save(data: dict) -> dict:
    cur = load()
    bad = [k for k, v in (data.get("colors") or {}).items() if not HEX.match(str(v))]
    if bad:
        return {"ok": False, "message": f"Colors must look like #1A2B3C: {', '.join(bad)}."}
    merged = {"schema": 1, "vibe": data.get("vibe", cur["vibe"]), "voice": {**cur["voice"], **(data.get("voice") or {})},
              "colors": {**cur["colors"], **(data.get("colors") or {})}, "fonts": {**cur["fonts"], **(data.get("fonts") or {})},
              "imagery": data.get("imagery", cur["imagery"]), "assets": cur["assets"], "applied": cur.get("applied")}
    FILE.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "message": "Brand saved. Apply it to update the book's outputs.", "brand": load()}


# ------------------------------------------------------------------ fonts on disk
def font_files(family: str) -> list[Path]:
    key = re.sub(r"\s+", "", family).lower()
    return sorted(p for p in FONTS_DIR.glob("*.[ot]tf") if re.sub(r"[\s_-]+", "", p.stem).lower().startswith(key)) \
        if FONTS_DIR.exists() else []


def _face(family: str, files: list[Path], rel_prefix: str) -> str:
    out = []
    for f in files:
        italic = "italic" in f.stem.lower()
        out.append(f'@font-face {{ font-family: "{family}"; src: url("{rel_prefix}{f.name}"); '
                   f'font-weight: 100 900; font-style: {"italic" if italic else "normal"}; font-display: swap; }}')
    return "\n".join(out)


def css(brand: dict, font_prefix: str = "../fonts/") -> str:
    """CSS overrides from the tokens (colors as custom properties, fonts as families)."""
    c, f = brand["colors"], brand["fonts"]
    lines = ["/* Generated by Book Builder from brand.json. Edit the brand in Design › Brand Kit, not here. */"]
    faces = [_face(fam, font_files(fam), font_prefix) for fam in {v for v in f.values() if v}]
    lines += [x for x in faces if x]
    props = []
    for token, (_, names, _) in COLOR_TOKENS.items():
        if c.get(token):
            props += [f"  {n}: {c[token]};" for n in names]
    if c.get("accent") and c.get("paper"):
        link = darken_to(c["accent"], c["paper"])
        props += [f"  --link: {link};", f"  --accent: {link};", f"  --focus: {link};"]
    if f.get("display"):
        props.append(f'  --display-font: "{f["display"]}", Georgia, serif;')
    if f.get("ui"):
        props.append(f'  --ui-font: "{f["ui"]}", system-ui, sans-serif;')
    if f.get("body"):
        props.append(f'  --body-font: "{f["body"]}", Georgia, serif;')
    lines.append(":root {\n" + "\n".join(props) + "\n}")
    if f.get("body"):
        lines.append(f'body {{ font-family: "{f["body"]}", Georgia, serif; }}')
    if f.get("display"):
        lines.append(f'h1, h2, h3 {{ font-family: "{f["display"]}", Georgia, serif; }}')
    return "\n".join(lines) + "\n"


def apply(targets: list[str]) -> dict:
    """Write the saved brand into the chosen outputs. Never touches manuscript text."""
    if not FILE.exists():
        return {"ok": False, "message": "Save the brand first."}
    b = load()
    done, notes = [], []
    missing = [fam for fam in set(b["fonts"].values()) if fam and not font_files(fam)]
    if missing:
        notes.append(f"Not installed in this book yet (install in Design › Fonts): {', '.join(sorted(missing))}. "
                     "Outputs fall back to a similar font until then.")
    if "pdf" in targets:
        colors = {COLOR_TOKENS[k][0]: v for k, v in b["colors"].items() if k in COLOR_TOKENS}
        fonts = {k: v for k, v in b["fonts"].items() if v and font_files(v)}
        r = I.set_typst_brand(fonts=fonts, colors=colors)
        if not r["ok"]:
            return r
        done.append("PDF")
    if "ebook" in targets:
        BRAND_CSS.parent.mkdir(parents=True, exist_ok=True)
        BRAND_CSS.write_text(css(b), encoding="utf-8")
        done.append("EPUB/HTML")
    if "website" in targets:
        done.append("website (on its next build)")
    saved = json.loads(FILE.read_text(encoding="utf-8"))
    saved["applied"] = {"at": time.time(), "targets": targets}
    FILE.write_text(json.dumps(saved, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "message": f"Applied to {', '.join(done)}. Rebuild to see it." + (" " + " ".join(notes) if notes else ""),
            "notes": notes}


def website_css(site_public: Path) -> str:
    """For tools/website.py: brand CSS for the site (copies the needed font files into the site)."""
    if not FILE.exists() or "website" not in ((load().get("applied") or {}).get("targets") or []):
        return "/* No book brand applied to the website. */\n"
    b = load()
    dest = site_public / "brand-fonts"
    for fam in {v for v in b["fonts"].values() if v}:
        for f in font_files(fam):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / f.name)
    return css(b, font_prefix="brand-fonts/").replace('url("brand-fonts/', 'url("/brand-fonts/')


# ------------------------------------------------------------------ assets
def save_asset(slot: str, name: str, data: bytes) -> dict:
    if slot not in ASSET_SLOTS:
        return {"ok": False, "message": "Unknown asset slot."}
    ext = next((e for magic, e in ASSET_TYPES.items() if data.startswith(magic)), None)
    if ext == ".webp" and data[8:12] != b"WEBP":
        ext = None
    if not ext:
        return {"ok": False, "message": "Use a PNG, JPEG or WebP image (SVG isn't accepted, because it can contain scripts)."}
    if len(data) > 20 * 1024 * 1024:
        return {"ok": False, "message": "Images must be under 20 MB."}
    folder = ROOT / "assets" / "branding"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{slot}{ext}"
    for old in folder.glob(f"{slot}.*"):              # keep what was there before
        prev = folder / ".previous"
        prev.mkdir(exist_ok=True)
        shutil.copy2(old, prev / f"{time.strftime('%Y%m%d-%H%M%S')}-{old.name}")
    target.write_bytes(data)
    saved = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {"schema": 1}
    saved.setdefault("assets", {})[slot] = target.relative_to(ROOT).as_posix()
    FILE.write_text(json.dumps(saved, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "path": target.relative_to(ROOT).as_posix(),
            "message": f"Saved the {ASSET_SLOTS[slot].lower()}." + (" The previous file was kept in assets/branding/.previous/." if any(folder.joinpath('.previous').glob(f'*-{slot}.*')) else "")}


STRATEGY_PROMPT = """# Brand strategy for a book: {title}

You're helping an author choose a visual and verbal identity for their book. It is used for the cover,
the printed PDF, the e-book and the book's website.

## About the book
- Title: {title}{subtitle}
- Author: {author}
- Genre / category: {subject}
- Audience: {audience}
- Description: {description}

## Current brand (may be blank)
{current}

## What to send back
Return ONE JSON object in a ```json code block, nothing else in the block:
{{"vibe": "one sentence", "voice": {{"tone": "...", "person": "first/second/third", "readingLevel": "...", "avoid": "..."}},
 "colors": {{"ink": "#RRGGBB", "paper": "#RRGGBB", "accent": "#RRGGBB", "highlight": "#RRGGBB", "secondary": "#RRGGBB",
            "text2": "#RRGGBB", "rule": "#RRGGBB"}},
 "fonts": {{"display": "Google Fonts family", "body": "Google Fonts family", "ui": "Google Fonts family"}},
 "imagery": "how illustrations and photos should look"}}

Rules: only free Google Fonts families; body text (ink on paper) needs contrast of at least 7:1 and the
accent at least 4.5:1 on paper; avoid stereotypes; explain your choices in 5 short bullets AFTER the JSON.
"""


def strategy_prompt() -> str:
    import bookmeta  # noqa: PLC0415
    m, b = bookmeta.book_meta(), load()
    cur = json.dumps({k: b[k] for k in ("vibe", "voice", "colors", "fonts", "imagery")}, indent=1, ensure_ascii=False)
    return STRATEGY_PROMPT.format(title=m.get("title") or "Untitled", subtitle=f": {m['subtitle']}" if m.get("subtitle") else "",
                                  author=m.get("author") or "", subject=m.get("subject") or "", audience=m.get("intended-audience") or "",
                                  description=m.get("description") or "", current=cur)


def parse_suggestion(text: str) -> dict:
    """Pull the JSON object out of an AI reply; keep only known, valid fields."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("No JSON object found in the reply.")
    data = json.loads(m.group(1))
    clean = {"vibe": str(data.get("vibe", ""))[:500], "imagery": str(data.get("imagery", ""))[:1000],
             "voice": {k: str(v)[:300] for k, v in (data.get("voice") or {}).items() if k in ("tone", "person", "readingLevel", "avoid")},
             "colors": {k: str(v).upper() for k, v in (data.get("colors") or {}).items() if k in COLOR_TOKENS and HEX.match(str(v))},
             "fonts": {k: str(v) for k, v in (data.get("fonts") or {}).items() if k in FONT_TOKENS and re.fullmatch(r"[A-Za-z0-9 ]{2,60}", str(v))}}
    return clean
