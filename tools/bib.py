#!/usr/bin/env python3
"""Build references.bib from the APA entries in research/chatgpt/.

The research step already records, for every source, a key and a full APA 7
reference. That is everything a bibliography needs, so the .bib file is
generated rather than maintained by hand: re-run this whenever new research
lands.

    python tools/bib.py            # write references.bib and report
    python tools/bib.py --check    # report only, write nothing
"""

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
RESEARCH = ROOT / "research" / "chatgpt"
BIB = ROOT / "references.bib"
DRAFTS = ROOT / "drafts"

ENTRY_RE = re.compile(
    r"^-\s*key:\s*(?P<key>\S+)\s*\n\s*apa:\s*\"(?P<apa>.+?)\"\s*\n(?P<rest>.*?)"
    r"(?=\n-\s*key:|\Z)", re.M | re.S)
TYPE_RE = re.compile(r"^\s*type:\s*\"?([\w -]+)\"?", re.M)
CITE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")

# research "type" -> BibTeX entry type
ARTICLE_TYPES = {"peer-reviewed", "review", "meta-analysis"}


def unlink(text: str) -> str:
    """[label](url) -> label, and drop ChatGPT's utm_source tracking."""
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1", text)
    return re.sub(r"[?&]utm_source=chatgpt\.com", "", text)


def escape(text: str) -> str:
    text = re.sub(r"\s*\[[^\]]{0,40}\]\s*$", "", text.strip())
    text = text.replace("\\", " ").replace("{", "").replace("}", "")
    for ch in "&%$#_":
        text = text.replace(ch, "\\" + ch)
    return re.sub(r"\s+", " ", text).strip().rstrip(".").strip()


def authors(raw: str) -> str:
    """APA 'Last, A. B., Other, C., & Third, D.' -> BibTeX 'and'-separated."""
    raw = raw.strip().rstrip(",").strip()
    people = re.findall(r"([^,&]+?),\s*((?:[A-Z]\.[\s-]*)+)", raw)
    if people:
        return " and ".join(f"{s.strip().lstrip('&').strip()}, {i.strip()}"
                            for s, i in people)
    return "{" + escape(raw) + "}"          # corporate author


def parse(key: str, apa: str, kind: str) -> dict | None:
    apa = unlink(apa).strip()
    url = ""
    m = re.search(r"(https?://\S+)", apa)
    if m:
        url = m.group(1).rstrip(" .)")
        apa = apa[:m.start()].strip()
    # APA requires a retrieval date on undated web pages.
    urldate = ""
    rm = re.search(r"Retrieved\s+([^,]+,\s*\d{4}),?\s*from\s*$", apa)
    if rm:
        urldate = rm.group(1).strip()
        apa = apa[:rm.start()].strip().rstrip(".").strip()

    m = re.match(r"^(?P<auth>.+?)\((?P<date>n\.\s?d\.|[^)]*?\d{4}[^)]*)\)\.?\s*(?P<rest>.*)$",
                 apa, re.S)
    if not m:
        return None
    rest = m.group("rest").strip()
    ym = re.search(r"\d{4}", m.group("date"))

    out = {"key": key, "author": authors(m.group("auth")),
           "year": ym.group(0) if ym else "n.d.", "url": url, "urldate": urldate}

    ital = re.search(r"\*(?P<it>[^*]+)\*", rest)
    if ital and ital.start() <= 1:
        # Web page / report: the TITLE is the italic part.
        out["title"] = escape(ital.group("it"))
        tail = rest[ital.end():].strip(" .")
        out["publisher"] = escape(tail.split(".")[0]) if tail else ""
        out["type"] = "misc"
    elif ital:
        # Journal article: italics cover "Journal, Volume".
        out["title"] = escape(rest[:ital.start()])
        jv = ital.group("it")
        jm = re.match(r"^(?P<j>.+?),\s*(?P<v>[\dSs()-]+)\s*$", jv)
        out["journal"] = escape(jm.group("j") if jm else jv)
        out["volume"] = (jm.group("v").strip() if jm else "")
        tail = rest[ital.end():]
        im = re.match(r"^\((?P<i>[^)]+)\)", tail.strip())
        out["number"] = im.group("i") if im else ""
        pm = re.search(r"(\d+)\s*[–—-]\s*(\d+)", tail)
        out["pages"] = f"{pm.group(1)}--{pm.group(2)}" if pm else ""
        out["type"] = "article"
    else:
        out["title"] = escape(rest.split(". ")[0])
        out["publisher"] = ""
        out["type"] = "misc"

    if kind not in ARTICLE_TYPES and out["type"] == "article" and not out.get("journal"):
        out["type"] = "misc"
    if "doi.org/" in url:
        out["doi"] = url.split("doi.org/", 1)[1]
    return out if out["title"] else None


def collect() -> tuple[dict, list[str]]:
    entries, bad = {}, []
    for path in sorted(RESEARCH.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for m in ENTRY_RE.finditer(text):
            key = m.group("key").strip().strip('"')
            if key in entries:
                continue
            t = TYPE_RE.search(m.group("rest"))
            rec = parse(key, m.group("apa"), (t.group(1).strip() if t else "other"))
            if rec:
                entries[key] = rec
            else:
                bad.append(f"{path.name}: {key}")
    return entries, bad


def render(e: dict) -> str:
    fields = [("author", e["author"]), ("title", "{" + e["title"] + "}"),
              ("year", e["year"])]
    for name in ("journal", "volume", "number", "pages", "publisher", "doi", "url",
                 "urldate"):
        if e.get(name):
            fields.append((name, e[name]))
    body = ",\n".join(f"  {k:9} = {{{v}}}" for k, v in fields)
    return f"@{e['type']}{{{e['key']},\n{body}\n}}\n"


def existing() -> dict[str, str]:
    """Hand-written entries already in references.bib, kept verbatim.

    Research does not cover every source (some were curated by hand, with
    copies under sources/), so generating must never silently drop them.
    """
    if not BIB.exists():
        return {}
    out, text = {}, BIB.read_text(encoding="utf-8")
    for m in re.finditer(r"^@\w+\s*\{\s*([^,\s]+)\s*,", text, re.M):
        start = m.start()
        depth, i = 0, text.index("{", start)
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = text[start:i + 1].rstrip() + "\n"
    return out


def cited() -> set[str]:
    keys = set()
    for p in DRAFTS.glob("*/v*-chapter.md"):
        keys |= set(CITE_RE.findall(p.read_text(encoding="utf-8")))
    return keys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()

    entries, bad = collect()
    kept = {k: v for k, v in existing().items() if k not in entries}
    used = cited()
    missing = sorted(used - set(entries) - set(kept))

    print(f"research entries parsed : {len(entries)}")
    print(f"unparseable             : {len(bad)}")
    for b in bad[:10]:
        print(f"    {b}")
    print(f"hand-written kept as-is : {len(kept)} ({', '.join(sorted(kept)) or '-'})")
    print(f"keys cited in drafts    : {len(used)}")
    print(f"cited but NOT in research (would still break the build): {len(missing)}")
    for k in missing[:20]:
        print(f"    @{k}")

    if args.check:
        return 1 if missing else 0

    blocks = {k: render(v) for k, v in entries.items()} | kept
    text = ("% Generated by tools/bib.py from research/chatgpt/.\n"
            "% Entries not covered by research are preserved verbatim; everything\n"
            "% else is regenerated, so re-run the tool after new research lands.\n\n"
            + "\n".join(blocks[k] for k in sorted(blocks)))
    BIB.write_text(text, encoding="utf-8")
    print(f"\nwrote {BIB.relative_to(ROOT)}: {len(blocks)} entries "
          f"({len(entries)} generated + {len(kept)} kept), {len(text):,} bytes")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
