"""Prompt packs: one prompt, delivered two ways. Project-agnostic (no book-specific code).

Every prompt the manager makes for a chat assistant (ChatGPT, or any other) is a Pack:

  - **Clipboard** (always enough on its own): the prompt text. It contains everything needed to do the
    task, so the author only has to paste it into a new chat. No Project, uploads or setup.
  - **ZIP** (optional, richer): the same prompt as `prompt.md` plus reference files (charter, research
    memory, documentation…). Attach the ZIP and paste the same prompt; the assistant uses the files as
    extra background.

The prompt text is identical in both forms: it ends with a short note that lists the pack's reference
files and says "if the ZIP is attached, use it; if not, carry on". That's what lets the clipboard alone
get started, while the ZIP is a strict add-on.

Projects register pack builders with `@kind(...)`; the manager lists them at /api/prompts/kinds, so new
steps (from "describe your idea" to "publish") plug in without changing the UI code.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ZIP_README = """# {name}

This is a prompt pack made by the Book Manager.

How to use it:
1. Start a new chat.
2. Attach this ZIP file.
3. Paste the prompt (the Book Manager already copied it to your clipboard; it's also `prompt.md` in
   this ZIP) and send.

The prompt works without the ZIP too. The files in `reference/` are extra background:

{listing}
"""


@dataclass
class Pack:
    kind: str                      # registered kind, e.g. "research"
    name: str                      # human name, also the chat name, e.g. "Ch 05 · Masking and burnout"
    prompt: str                    # complete, self-contained prompt
    files: dict[str, bytes | str | Path] = field(default_factory=dict)   # reference/<name> -> content
    notes: dict[str, str] = field(default_factory=dict)                  # reference/<name> -> one-line description
    reply: str = ""                # one line: how the reply comes back (shown in the manager)

    @property
    def filename(self) -> str:
        return f"{slug(self.name)}-{self.kind}-pack.zip"

    def text(self) -> str:
        """The prompt as copied to the clipboard (and saved as prompt.md in the ZIP)."""
        if not self.files:
            return self.prompt.rstrip() + "\n"
        return self.prompt.rstrip() + "\n\n---\n\n" + self.pack_note() + "\n"

    def pack_note(self) -> str:
        lines = "\n".join(f"- `reference/{n}`" + (f": {self.notes[n]}" if n in self.notes else "")
                          for n in sorted(self.files))
        return ("## Optional reference pack\n\n"
                f"This prompt also comes as a ZIP file, `{self.filename}`, holding the reference files below. "
                "If that ZIP is attached to this message, open it and use these files as background; this "
                "message's instructions come first. If nothing is attached, don't ask for it: everything you "
                f"need is in this message.\n\n{lines}")

    def size(self) -> int:
        return sum(len(_bytes(v)) for v in self.files.values())

    def to_zip(self) -> bytes:
        buf = io.BytesIO()
        listing = "\n".join(f"- reference/{n}" + (f": {self.notes[n]}" if n in self.notes else "")
                            for n in sorted(self.files))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.md", ZIP_README.format(name=self.name, listing=listing or "- (none)"))
            zf.writestr("prompt.md", self.text())
            for n, v in sorted(self.files.items()):
                zf.writestr(f"reference/{n}", _bytes(v))
        return buf.getvalue()

    def summary(self) -> dict:
        return {"kind": self.kind, "name": self.name, "chars": len(self.text()), "words": len(self.text().split()),
                "files": sorted(self.files), "zipName": self.filename, "zipBytes": self.size(), "reply": self.reply}


def _bytes(v: bytes | str | Path) -> bytes:
    if isinstance(v, Path):
        return v.read_bytes()
    return v.encode("utf-8") if isinstance(v, str) else v


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60].rstrip("-") or "prompt"


# ------------------------------------------------------------------ registry

@dataclass
class Kind:
    id: str
    title: str
    stage: str                     # where it sits in the workflow, e.g. "plan", "research", "write", "extras"
    needs: str                     # what it takes: "none", "chapter", "chapter-with-draft", "chapter-with-review"
    build: Callable[..., Pack]
    description: str = ""


KINDS: dict[str, Kind] = {}


def kind(id: str, title: str, stage: str, needs: str = "chapter", description: str = ""):
    def deco(fn: Callable[..., Pack]) -> Callable[..., Pack]:
        KINDS[id] = Kind(id, title, stage, needs, fn, description)
        return fn
    return deco


def make(kind_id: str, **args) -> Pack:
    if kind_id not in KINDS:
        raise KeyError(f"Unknown prompt kind {kind_id!r}. Known: {', '.join(KINDS)}")
    return KINDS[kind_id].build(**args)


def kinds() -> list[dict]:
    return [{"id": k.id, "title": k.title, "stage": k.stage, "needs": k.needs, "description": k.description}
            for k in KINDS.values()]
