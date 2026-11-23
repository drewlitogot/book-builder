"""Google Fonts for book projects: search the free catalog and install font files into a project.

The catalog comes from Google Fonts' public metadata and is cached in BOOK_BUILDER_HOME for a week.
If it can't be fetched (offline, or turned off in Settings › Privacy) a short built-in list is used.
Installing downloads the family's TTF files and license from the google/fonts repository into the
project's assets/fonts, where the PDF build (Typst) finds them.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

import registry as R

CATALOG_URL = "https://fonts.google.com/metadata/fonts"
RAW = "https://raw.githubusercontent.com/google/fonts/main/{lic}/{dir}/{file}"
CACHE = R.HOME / "fonts-catalog.json"
AGENT = {"User-Agent": "BookBuilder/1.0"}

FALLBACK = [  # (family, category) used when the catalog can't be fetched
    ("Playfair Display", "Serif"), ("Source Serif 4", "Serif"), ("Source Sans 3", "Sans Serif"),
    ("Atkinson Hyperlegible", "Sans Serif"), ("Literata", "Serif"), ("Merriweather", "Serif"),
    ("Lora", "Serif"), ("EB Garamond", "Serif"), ("Crimson Pro", "Serif"), ("Libre Baskerville", "Serif"),
    ("Cormorant Garamond", "Serif"), ("Alegreya", "Serif"), ("Noto Serif", "Serif"), ("Inter", "Sans Serif"),
    ("Open Sans", "Sans Serif"), ("Lato", "Sans Serif"), ("Roboto", "Sans Serif"), ("Work Sans", "Sans Serif"),
    ("Nunito Sans", "Sans Serif"), ("IBM Plex Sans", "Sans Serif"), ("Libre Franklin", "Sans Serif"),
    ("DM Serif Display", "Serif"), ("Abril Fatface", "Display"), ("Bebas Neue", "Display"),
    ("JetBrains Mono", "Monospace"), ("Caveat", "Handwriting"),
]


def _get(url: str, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as r:  # noqa: S310
        return r.read()


def catalog(allow_network: bool = True) -> dict:
    """{source, families: [{family, category, variants}]}; source is 'google', 'cache' or 'built-in'."""
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - cached.get("time", 0) < 7 * 86400:
            return {"source": "cache", "families": cached["families"]}
    except (OSError, ValueError, KeyError):
        cached = None
    if allow_network:
        try:
            raw = _get(CATALOG_URL).decode("utf-8")
            data = json.loads(raw[raw.index("{"):])
            fams = [{"family": f["family"], "category": f.get("category", ""),
                     "variants": len(f.get("fonts", {}))} for f in data.get("familyMetadataList", [])]
            if fams:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps({"time": time.time(), "families": fams}), encoding="utf-8")
                return {"source": "google", "families": fams}
        except (OSError, ValueError) as e:
            err = str(e)
        else:
            err = "empty catalog"
    else:
        err = "turned off in Settings › Privacy"
    if cached:
        return {"source": "cache", "families": cached["families"], "note": f"Using an older copy ({err})."}
    return {"source": "built-in", "families": [{"family": f, "category": c, "variants": 0} for f, c in FALLBACK],
            "note": f"Showing a short built-in list: the Google Fonts catalog isn't available ({err})."}


def install(family: str, dest: Path) -> dict:
    """Download a family's font files and license into dest (a project's assets/fonts)."""
    if not re.fullmatch(r"[A-Za-z0-9 ]{2,60}", family or ""):
        return {"ok": False, "message": "That isn't a valid font family name."}
    d = family.lower().replace(" ", "")
    meta, lic = None, None
    for lic in ("ofl", "apache", "ufl"):
        try:
            meta = _get(RAW.format(lic=lic, dir=d, file="METADATA.pb")).decode("utf-8")
            break
        except OSError:
            continue
    if not meta:
        return {"ok": False, "message": f"Couldn't find {family} in the Google Fonts repository (or you're offline)."}
    files = sorted(set(re.findall(r'filename:\s*"([^"]+\.ttf)"', meta)))
    if not files:
        return {"ok": False, "message": f"{family} has no TTF files listed."}
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    try:
        for f in files:
            # Keep the file names Typst and pandoc already accept; drop the [axis] suffix for tidiness.
            out = dest / re.sub(r"\[[^\]]+\]", "", f)
            out.write_bytes(_get(RAW.format(lic=lic, dir=d, file=f), timeout=60))
            saved.append(out.name)
        lic_name = {"ofl": "OFL.txt", "apache": "LICENSE.txt", "ufl": "UFL.txt"}[lic]
        try:
            (dest / f"{family.replace(' ', '')}-{lic_name}").write_bytes(_get(RAW.format(lic=lic, dir=d, file=lic_name)))
        except OSError:
            pass
    except OSError as e:
        return {"ok": False, "message": f"Download failed after {len(saved)} file(s): {e}"}
    return {"ok": True, "message": f"Installed {family} ({len(saved)} file{'s' if len(saved) != 1 else ''}) into assets/fonts.",
            "files": saved}
