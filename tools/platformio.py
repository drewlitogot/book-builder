"""Clipboard and "open in the system" helpers for macOS, Windows and Linux.

macOS uses pbcopy/pbpaste/open (unchanged behaviour). Windows uses clip, PowerShell Get-Clipboard and
os.startfile / explorer. Linux uses wl-copy/xclip and xdg-open when available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

MAC, WIN = sys.platform == "darwin", os.name == "nt"


def copy(text: str) -> None:
    if MAC:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    elif WIN:
        subprocess.run(["clip"], input=text.encode("utf-16"), check=True)   # UTF-16 with BOM keeps Unicode intact
    elif shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
    elif shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
    else:
        raise RuntimeError("No clipboard tool found (install wl-clipboard or xclip).")


def paste() -> str:
    if MAC:
        return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    if WIN:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n").rstrip("\n")
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"]):
        if shutil.which(cmd[0]):
            return subprocess.run(cmd, capture_output=True, text=True).stdout
    raise RuntimeError("No clipboard tool found (install wl-clipboard or xclip).")


def open_path(path: Path, reveal: bool = False) -> None:
    p = str(path)
    if MAC:
        subprocess.run(["open", *(["-R"] if reveal else []), p])
    elif WIN:
        if reveal:
            subprocess.run(["explorer", f"/select,{p}"])
        else:
            os.startfile(p)  # noqa: S606
    else:
        subprocess.run(["xdg-open", str(Path(p).parent if reveal else p)])
