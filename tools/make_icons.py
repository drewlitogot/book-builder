#!/usr/bin/env python3
"""Build the Book Manager's icon sprite (tools/web/icons.svg) from Lucide's static SVGs.

Lucide (https://lucide.dev) is open source under the ISC license; its license is copied to
tools/web/ICONS-LICENSE.txt. The sprite is committed, so this only runs when icons are added:

    npm pack lucide-static@0.460.0 && tar xzf lucide-static-0.460.0.tgz
    python tools/make_icons.py package
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
ICONS = [
    "library-big", "package-check", "git-commit-horizontal", "lock",
    "activity", "archive", "arrow-right", "arrow-up-down", "baby", "badge-check", "book-copy",
    "book-marked", "book-open", "book-plus", "book-text", "bot", "brain", "chart-column",
    "check-check", "chevron-down", "chevron-left", "chevron-right", "circle-alert", "circle-check",
    "circle-help", "circle-minus", "circle-plus", "circle-x", "clipboard-check", "clipboard-copy",
    "clipboard-paste", "clock-3", "cloud-upload", "download", "ellipsis", "external-link", "eye",
    "feather", "file", "file-archive", "file-pen-line", "file-plus", "file-text", "file-type",
    "file-up", "file-warning", "folder", "folder-input", "folder-open", "gamepad-2", "git-compare",
    "github", "globe", "graduation-cap", "hammer", "heart-pulse", "history", "house", "image", "info",
    "layers", "layout-dashboard", "layout-grid", "layout-template", "library", "link", "list-checks",
    "list-tree", "mail", "menu", "message-square", "monitor", "package", "palette", "panel-left",
    "pen-line", "pencil-line", "play", "plus", "power", "puzzle", "refresh-cw", "rocket", "save",
    "scan-eye", "scan-search", "search", "search-check", "server", "settings", "settings-2", "shield",
    "shield-check", "skip-forward", "sliders-horizontal", "sparkles", "sun-moon", "swatch-book", "tag",
    "trash-2", "triangle-alert", "type", "undo-2", "upload", "wand-sparkles", "workflow", "x",
]


def main() -> None:
    pkg = Path(sys.argv[1] if len(sys.argv) > 1 else "package")
    symbols = []
    for name in ICONS:
        svg = (pkg / "icons" / f"{name}.svg").read_text(encoding="utf-8")
        inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        inner = re.sub(r"\s+", " ", inner).strip()
        symbols.append(f'<symbol id="{name}" viewBox="0 0 24 24">{inner}</symbol>')
    version = __import__("json").loads((pkg / "package.json").read_text())["version"]
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">\n<!-- Lucide {version}, ISC license: see ICONS-LICENSE.txt -->\n'
           + "\n".join(symbols) + "\n</svg>\n")
    (WEB / "icons.svg").write_text(out, encoding="utf-8")
    (WEB / "ICONS-LICENSE.txt").write_text(f"Icons: Lucide {version} (https://lucide.dev)\n\n"
                                           + (pkg / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{len(symbols)} icons -> {(WEB / 'icons.svg')}")


if __name__ == "__main__":
    main()
