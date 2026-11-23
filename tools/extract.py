"""Extract searchable text from research documents, keeping page / sheet / slide / section references.

Standard library only, plus `pdftotext` (Poppler) for PDFs when it's installed. Documents are
untrusted: Office/ODF/EPUB files are read as ZIP + XML (macros are never run), archives go through
the same safety checks as update packages, and anything that can't be read is flagged, never dropped.

extract(path) -> {"status": ok|partial|unsupported|scanned|error, "note": str,
                  "segments": [{"ref": "Page 3" | "Sheet: Data" | "Slide 8" | "Section 2", "text": str}],
                  "media": [notes about embedded media that wasn't indexed]}
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from bbmanage import zipsafe

SUPPORTED = {".pdf", ".docx", ".docm", ".txt", ".md", ".markdown", ".rtf", ".odt", ".html", ".htm", ".csv",
             ".xlsx", ".xlsm", ".json", ".epub", ".pptx", ".pptm"}
LEGACY = {".doc": "Word 97–2003", ".xls": "Excel 97–2003", ".ppt": "PowerPoint 97–2003"}
MAX_SEGMENT = 6000
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}


def result(status: str, segments: list[dict], note: str = "", media: list[str] | None = None) -> dict:
    segs = []
    for s in segments:
        t = re.sub(r"[ \t]+", " ", s["text"]).strip()
        t = re.sub(r"\n{3,}", "\n\n", t)
        for i in range(0, len(t), MAX_SEGMENT):          # long sections are split, keeping the reference
            segs.append({"ref": s["ref"] + (f" (part {i // MAX_SEGMENT + 1})" if len(t) > MAX_SEGMENT else ""),
                         "text": t[i:i + MAX_SEGMENT]})
    segs = [s for s in segs if s["text"]]
    if status == "ok" and not segs:
        status, note = "partial", note or "No text found."
    return {"status": status, "note": note, "segments": segs, "media": media or []}


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(z.read(name))                # expat: no external entities, no network
    except (KeyError, ET.ParseError):
        return None


def _open_zip(path: Path) -> zipfile.ZipFile:
    zipsafe.check(path, max_total=400 * 1024 ** 2)
    return zipfile.ZipFile(path)


# ------------------------------------------------------------------ plain formats
def _text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def plain(path: Path) -> dict:
    text = _text(path)
    if path.suffix.lower() in (".md", ".markdown"):
        parts = re.split(r"(?m)^(#{1,3} .+)$", text)
        segs, head = [], "Start"
        if parts[0].strip():
            segs.append({"ref": "Start", "text": parts[0]})
        for i in range(1, len(parts), 2):
            head = parts[i].lstrip("# ").strip()
            segs.append({"ref": f"Section: {head[:80]}", "text": parts[i] + "\n" + parts[i + 1]})
        return result("ok", segs)
    paras = re.split(r"\n\s*\n", text)
    return result("ok", _chunks(paras, "Part"))


def _chunks(paras: list[str], label: str, size: int = 4000) -> list[dict]:
    segs, cur, n = [], "", 1
    for p in paras:
        if len(cur) + len(p) > size and cur:
            segs.append({"ref": f"{label} {n}", "text": cur}); n += 1; cur = ""
        cur += p.strip() + "\n\n"
    if cur.strip():
        segs.append({"ref": f"{label} {n}", "text": cur})
    return segs


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.sections = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in ("h1", "h2", "h3"):
            self.sections.append(("".join(self.out), None)); self.out = []
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.out.append(f" [Image: {alt}] ")
        elif tag in ("p", "br", "li", "tr", "div"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_text(source: str) -> list[dict]:
    p = _HTML()
    p.feed(source)
    p.sections.append(("".join(p.out), None))
    texts = [t for t, _ in p.sections if t.strip()]
    return [{"ref": f"Section {i}", "text": t} for i, t in enumerate(texts, 1)]


def rtf(path: Path) -> dict:
    s = _text(path)
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252"), s)
    s = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), s)
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)                       # ignorable destinations
    s = re.sub(r"\{\\(fonttbl|colortbl|stylesheet|info|pict)[^{}]*(\{[^{}]*\}[^{}]*)*\}", "", s)
    s = re.sub(r"\\(par|line)\b ?", "\n", s)
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)
    s = s.replace("{", "").replace("}", "").replace("\\\\", "\\")
    return result("ok", _chunks(re.split(r"\n\s*\n", s), "Part"), "RTF formatting removed.")


def csv_file(path: Path) -> dict:
    text = _text(path)
    rows = list(csv.reader(io.StringIO(text)))
    lines = [" | ".join(r) for r in rows]
    return result("ok", [{"ref": f"Rows {i + 1}–{min(i + 200, len(lines))}", "text": "\n".join(lines[i:i + 200])}
                         for i in range(0, len(lines), 200)])


def json_file(path: Path) -> dict:
    try:
        data = json.loads(_text(path))
    except ValueError as e:
        return result("partial", [{"ref": "Raw", "text": _text(path)}], f"Not valid JSON ({e}); indexed as text.")
    flat = []

    def walk(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{key}.{k}" if key else str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{key}[{i}]")
        elif isinstance(v, str) and v.strip():
            flat.append(f"{key}: {v}")
        elif v is not None and not isinstance(v, str):
            flat.append(f"{key}: {v}")
    walk(data)
    return result("ok", _chunks(flat, "Part"))


# ------------------------------------------------------------------ PDF
def pdf(path: Path) -> dict:
    exe = shutil.which("pdftotext")
    if not exe:
        return result("unsupported", [], "PDF text extraction needs pdftotext (Poppler): install it, then re-index. The original is kept.")
    try:
        r = subprocess.run([exe, "-enc", "UTF-8", "-layout", str(path), "-"], capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return result("error", [], "pdftotext timed out. The original is kept.")
    if r.returncode:
        msg = r.stderr.decode(errors="replace").strip()[:200]
        if "password" in msg.lower() or "encrypt" in msg.lower():
            return result("unsupported", [], "Password-protected PDF: text can't be extracted. The original is kept.")
        return result("error", [], f"pdftotext failed: {msg}")
    pages = r.stdout.decode("utf-8", errors="replace").split("\f")
    segs = [{"ref": f"Page {i}", "text": t} for i, t in enumerate(pages, 1) if t.strip()]
    if not segs:
        return result("scanned", [], "No text layer (probably a scanned PDF). It needs OCR before it can be searched. The original is kept.")
    empty = sum(1 for t in pages[:-1] if not t.strip())
    return result("partial" if empty > len(pages) / 3 else "ok", segs,
                  f"{empty} page(s) had no text (scanned images?)." if empty else "")


# ------------------------------------------------------------------ Office Open XML / ODF / EPUB
def docx(path: Path) -> dict:
    with _open_zip(path) as z:
        root = _xml(z, "word/document.xml")
        if root is None:
            return result("error", [], "Not a valid Word document (word/document.xml missing).")
        segs, cur, head, n = [], [], "Start", 0
        media = [f"{len([x for x in z.namelist() if x.startswith('word/media/')])} embedded image(s) not indexed"] \
            if any(x.startswith("word/media/") for x in z.namelist()) else []
        for para in root.iter(f"{{{NS['w']}}}p"):
            style = para.find(f".//{{{NS['w']}}}pStyle")
            text = "".join(t.text or "" for t in para.iter(f"{{{NS['w']}}}t"))
            if style is not None and re.match(r"Heading[1-3]|Title", style.get(f"{{{NS['w']}}}val", "")) and text.strip():
                if cur:
                    segs.append({"ref": f"Section: {head[:80]}" if n else "Start", "text": "\n".join(cur)})
                head, cur, n = text.strip(), [text], n + 1
            elif text.strip():
                cur.append(text)
        if cur:
            segs.append({"ref": f"Section: {head[:80]}" if n else "Start", "text": "\n".join(cur)})
        note = "Macros (if any) were ignored." if path.suffix.lower() == ".docm" else ""
        return result("ok", segs, note, media)


def odt(path: Path) -> dict:
    with _open_zip(path) as z:
        root = _xml(z, "content.xml")
        if root is None:
            return result("error", [], "Not a valid OpenDocument file (content.xml missing).")
        paras = ["".join(el.itertext()) for el in root.iter() if el.tag in (f"{{{NS['text']}}}p", f"{{{NS['text']}}}h")]
        return result("ok", _chunks([p for p in paras if p.strip()], "Part"))


def xlsx(path: Path) -> dict:
    with _open_zip(path) as z:
        shared = []
        sroot = _xml(z, "xl/sharedStrings.xml")
        if sroot is not None:
            shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['s']}}}t")) for si in sroot.findall("s:si", NS)]
        wb = _xml(z, "xl/workbook.xml")
        rels = _xml(z, "xl/_rels/workbook.xml.rels")
        if wb is None:
            return result("error", [], "Not a valid Excel workbook.")
        targets = {r.get("Id"): r.get("Target") for r in rels} if rels is not None else {}
        segs = []
        for sheet in wb.iter(f"{{{NS['s']}}}sheet"):
            name = sheet.get("name")
            target = targets.get(sheet.get(f"{{{NS['r']}}}id"), "")
            target = target.lstrip("/").removeprefix("xl/")
            root = _xml(z, "xl/" + target) if target else None
            if root is None:
                continue
            lines = []
            for row in root.iter(f"{{{NS['s']}}}row"):
                vals = []
                for c in row.findall("s:c", NS):
                    v = c.find("s:v", NS)
                    inline = c.find(".//s:t", NS)
                    if c.get("t") == "s" and v is not None and v.text and v.text.isdigit() and int(v.text) < len(shared):
                        vals.append(shared[int(v.text)])
                    elif inline is not None:
                        vals.append(inline.text or "")
                    elif v is not None:
                        vals.append(v.text or "")
                if any(vals):
                    lines.append(" | ".join(vals))
            for i in range(0, len(lines), 200):
                segs.append({"ref": f"Sheet: {name}" + (f", rows {i + 1}–{i + len(lines[i:i + 200])}" if len(lines) > 200 else ""),
                             "text": "\n".join(lines[i:i + 200])})
        note = "Formulas show their last saved values; macros (if any) were ignored." if path.suffix.lower() == ".xlsm" \
            else "Formulas show their last saved values."
        return result("ok", segs, note)


def epub(path: Path) -> dict:
    with _open_zip(path) as z:
        container = _xml(z, "META-INF/container.xml")
        opf_path = None
        if container is not None:
            for el in container.iter():
                if el.tag.endswith("rootfile"):
                    opf_path = el.get("full-path")
        opf = _xml(z, opf_path) if opf_path else None
        if opf is None:
            return result("error", [], "Not a valid EPUB (no package document).")
        base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
        items = {i.get("id"): i.get("href") for i in opf.iter() if i.tag.endswith("item")}
        order = [items.get(r.get("idref")) for r in opf.iter() if r.tag.endswith("itemref")]
        segs = []
        for i, href in enumerate([h for h in order if h], 1):
            try:
                doc = z.read(base + href).decode("utf-8", errors="replace")
            except KeyError:
                continue
            text = " ".join(s["text"] for s in html_text(doc))
            if text.strip():
                segs.append({"ref": f"Chapter {i} ({href.rsplit('/', 1)[-1]})", "text": text})
        return result("ok", segs)


def pptx(path: Path) -> dict:
    """Slide text, tables, image descriptions and speaker notes, one segment per slide ("Slide 8")."""
    with _open_zip(path) as z:
        pres = _xml(z, "ppt/presentation.xml")
        rels = _xml(z, "ppt/_rels/presentation.xml.rels")
        if pres is None or rels is None:
            return result("error", [], "Not a valid PowerPoint file.")
        targets = {r.get("Id"): r.get("Target") for r in rels}
        slides = [targets.get(s.get(f"{{{NS['r']}}}id")) for s in pres.iter(f"{{{NS['p']}}}sldId")]
        segs, media = [], []
        for n, target in enumerate([s for s in slides if s], 1):
            spath = "ppt/" + target.lstrip("/").removeprefix("ppt/")
            root = _xml(z, spath)
            if root is None:
                continue
            parts = []
            for sp in root.iter():
                tag = sp.tag.rsplit("}", 1)[-1]
                if sp.tag == f"{{{NS['p']}}}txBody":           # shape text (table cells use a:txBody, handled below)
                    paras = ["".join(t.text or "" for t in para.iter(f"{{{NS['a']}}}t")) for para in sp.iter(f"{{{NS['a']}}}p")]
                    txt = "\n".join(p for p in paras if p.strip())
                    if txt:
                        parts.append(txt)
                elif tag == "cNvPr" and (sp.get("descr") or "").strip():
                    parts.append(f"[Image description: {sp.get('descr').strip()}]")
            tables = []
            for tbl in root.iter(f"{{{NS['a']}}}tbl"):
                rows = [" | ".join("".join(t.text or "" for t in tc.iter(f"{{{NS['a']}}}t")) for tc in tr.iter(f"{{{NS['a']}}}tc"))
                        for tr in tbl.iter(f"{{{NS['a']}}}tr")]
                tables.append("Table:\n" + "\n".join(rows))
            # speaker notes via the slide's relationships
            notes = ""
            srels = _xml(z, spath.rsplit("/", 1)[0] + "/_rels/" + spath.rsplit("/", 1)[1] + ".rels")
            if srels is not None:
                for r in srels:
                    t, typ = r.get("Target", ""), r.get("Type", "")
                    if typ.endswith("/notesSlide"):
                        nroot = _xml(z, "ppt/" + t.replace("../", ""))
                        if nroot is not None:
                            notes = "\n".join("".join(x.text or "" for x in para.iter(f"{{{NS['a']}}}t"))
                                              for para in nroot.iter(f"{{{NS['a']}}}p")).strip()
                            notes = re.sub(r"^\d+$", "", notes, flags=re.M).strip()   # drop the slide-number placeholder
                    elif typ.endswith(("/video", "/audio", "/media", "/oleObject")):
                        media.append(f"Slide {n}: embedded {typ.rsplit('/', 1)[-1]} not indexed")
            body = "\n".join(parts + tables)
            if notes:
                body += f"\n\nSpeaker notes:\n{notes}"
            segs.append({"ref": f"Slide {n}", "text": body or "(no text on this slide)"})
        note = "Macros (if any) were ignored." if path.suffix.lower() == ".pptm" else ""
        return result("ok", segs, note, media)


# ------------------------------------------------------------------ entry point
def legacy(path: Path) -> dict:
    """.doc/.xls/.ppt: macOS's textutil can read .doc; nothing in the standard library reads the others."""
    kind = LEGACY[path.suffix.lower()]
    if path.suffix.lower() == ".doc" and shutil.which("textutil"):
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True, timeout=120)
        if r.returncode == 0:
            return result("ok", _chunks(re.split(r"\n\s*\n", r.stdout.decode("utf-8", errors="replace")), "Part"),
                          "Converted with macOS textutil.")
    return result("unsupported", [], f"{kind} files aren't read directly. The original is kept; save it as "
                  f"{'.pptx' if path.suffix.lower() == '.ppt' else '.xlsx' if path.suffix.lower() == '.xls' else '.docx'} "
                  "and upload that to make it searchable.")


def extract(path: Path) -> dict:
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md", ".markdown"):
            return plain(path)
        if ext in (".html", ".htm"):
            return result("ok", html_text(_text(path)))
        if ext == ".rtf":
            return rtf(path)
        if ext == ".csv":
            return csv_file(path)
        if ext == ".json":
            return json_file(path)
        if ext == ".pdf":
            return pdf(path)
        if ext in (".docx", ".docm"):
            return docx(path)
        if ext == ".odt":
            return odt(path)
        if ext in (".xlsx", ".xlsm"):
            return xlsx(path)
        if ext == ".epub":
            return epub(path)
        if ext in (".pptx", ".pptm"):
            return pptx(path)
        if ext in LEGACY:
            return legacy(path)
        return result("unsupported", [], f"{ext or 'This file type'} isn't supported for text search. The original is kept.")
    except zipsafe.UnsafeArchive as e:
        return result("error", [], f"Refused: {e}. The original is kept but not opened.")
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError, UnicodeError) as e:
        return result("error", [], f"Couldn't read the file ({e.__class__.__name__}: {str(e)[:150]}). The original is kept.")


def text_extract(text: str) -> dict:
    """For pasted research (clipboard): Markdown sections."""
    parts = re.split(r"(?m)^(#{1,3} .+)$", text)
    segs = [{"ref": "Start", "text": parts[0]}] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        segs.append({"ref": f"Section: {parts[i].lstrip('# ').strip()[:80]}", "text": parts[i] + "\n" + parts[i + 1]})
    return result("ok", segs)
