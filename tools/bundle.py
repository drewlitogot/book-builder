#!/usr/bin/env python3
"""Bundle an agent prompt and all its inputs into one paste-ready Markdown file.

Usage:
    python tools/bundle.py ROLE CHAPTER_ID [--perspective P] [--neurotype N]

Examples:
    python tools/bundle.py factchecker 02-boundaries-and-consent/10-saying-boundaries
    python tools/bundle.py perspective-reviewer 02-boundaries-and-consent/10-saying-boundaries --perspective women

Writes dist/bundles/<chapter>/<role>[-<param>].md. Paste the whole file into ChatGPT
(or any chat model), then save its reply to the path named at the top of the bundle.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Run: pip install -r requirements.txt")

ROOT = Path(os.environ.get("BOOK_PROJECT") or Path(__file__).resolve().parent.parent).resolve()  # the book project
CHARTER = "research/02-editorial-charter.md"
OUTLINE = "research/03-content-outline.md"

# role -> (inputs, output path template)
ROLES = {
    "researcher": (["outline", "evidence", "archive", "sources"], "sources/<key>/ (meta.yml + notes.md) and a research summary"),
    "brief-writer": (["charter", "outline", "sources"], "briefs/{ch}.md"),
    "drafter": (["charter", "brief", "sources"], "book/{ch}.md"),
    "factchecker": (["chapter", "sources"], "reviews/{ch}/factcheck.md"),
    "charter-reviewer": (["charter", "chapter"], "reviews/{ch}/charter.md"),
    "perspective-reviewer": (["charter", "chapter"], "reviews/{ch}/perspective-{perspective}.md"),
    "neurotype-reviewer": (["charter", "chapter"], "reviews/{ch}/neurotype-{neurotype}.md"),
    "plain-language": (["chapter"], "reviews/{ch}/plain-language.md"),
    "reviser": (["charter", "brief", "chapter", "reviews", "sources"], "book/{ch}.md and reviews/{ch}/changes.md"),
}

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def chapter_sources(ch: str) -> list[str]:
    path = ROOT / f"book/{ch}.md"
    if not path.exists():
        path = ROOT / f"briefs/{ch}.md"
    if not path.exists():
        return []
    m = FRONT_MATTER_RE.match(path.read_text(encoding="utf-8"))
    meta = yaml.safe_load(m.group(1)) if m else {}
    keys = meta.get("sources") or []
    if not keys:  # brief: pull keys from the claims table
        keys = sorted(set(re.findall(r"\b([a-z]+\d{4}[a-z]?)\b", path.read_text(encoding="utf-8"))))
    return [k for k in keys if (ROOT / "sources" / k).is_dir()]


def section(title: str, rel: str) -> str:
    return f"\n\n---\n\n## INPUT: `{rel}`\n\n````markdown\n{read(rel).rstrip()}\n````\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("role", choices=sorted(ROLES))
    p.add_argument("chapter", help="chapter id, e.g. 02-boundaries-and-consent/10-saying-boundaries")
    p.add_argument("--perspective", choices=["men", "women", "nonbinary"])
    p.add_argument("--neurotype", metavar="GROUP")
    a = p.parse_args()

    if a.role == "perspective-reviewer" and not a.perspective:
        p.error("perspective-reviewer needs --perspective")
    if a.role == "neurotype-reviewer" and not a.neurotype:
        p.error("neurotype-reviewer needs --neurotype")

    ch = a.chapter.removesuffix(".md").removeprefix("book/")
    inputs, out_tmpl = ROLES[a.role]
    out_path = out_tmpl.format(ch=ch, perspective=a.perspective, neurotype=a.neurotype)

    title = ""
    chapter_file = ROOT / f"book/{ch}.md"
    if chapter_file.exists():
        m = FRONT_MATTER_RE.match(chapter_file.read_text(encoding="utf-8"))
        title = (yaml.safe_load(m.group(1)) or {}).get("title", "") if m else ""

    prompt = read(f"agents/{a.role}.md")
    for k, v in {"chapter_id": ch, "chapter_title": title,
                 "perspective": a.perspective or "", "neurotype": a.neurotype or ""}.items():
        prompt = prompt.replace("{{" + k + "}}", v)

    parts = [
        f"<!-- Bundle for role `{a.role}`, chapter `{ch}`. Save the model's reply to: {out_path} -->\n",
        prompt.rstrip(),
        "\n\n---\n\n# Inputs\n\nAll inputs are below, each labeled with its repo path.",
    ]
    for inp in inputs:
        if inp == "charter":
            parts.append(section("charter", CHARTER))
        elif inp == "outline":
            parts.append(section("outline", OUTLINE))
        elif inp == "evidence":
            parts.append(section("evidence", "research/04-evidence-base.md"))
        elif inp == "archive":
            parts.append(section("archive", "research/07-source-archive.md"))
        elif inp == "brief":
            parts.append(section("brief", f"briefs/{ch}.md"))
        elif inp == "chapter":
            parts.append(section("chapter", f"book/{ch}.md"))
        elif inp == "sources":
            for key in chapter_sources(ch):
                for f in ("meta.yml", "notes.md"):
                    rel = f"sources/{key}/{f}"
                    if (ROOT / rel).exists():
                        parts.append(section(key, rel))
        elif inp == "reviews":
            for f in sorted((ROOT / f"reviews/{ch}").glob("*.md")):
                parts.append(section("review", f.relative_to(ROOT).as_posix()))

    suffix = f"-{a.perspective or a.neurotype}" if (a.perspective or a.neurotype) else ""
    out = ROOT / "dist/bundles" / ch / f"{a.role}{suffix}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"{out.relative_to(ROOT)}  →  save reply to {out_path}")


if __name__ == "__main__":
    main()
