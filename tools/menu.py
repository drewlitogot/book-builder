#!/usr/bin/env python3
"""Click-through menu for the chapter workflow (macOS dialogs). Started by run/Old menu.command.

The top button always does the next step for the current chapter, worked out from the files:
  no prompt yet          -> copy the writing prompt
  prompt, no draft       -> save ChatGPT's reply from the clipboard
  draft has problems     -> explain them and save a fixed reply
  draft, not checked     -> copy a message asking Claude to check it
  checked, needs changes -> copy the revision prompt, then save the reply
  checked, ready         -> approve, then move to the next chapter
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chapter as C  # noqa: E402

ROOT = C.ROOT
PY = sys.executable
TITLE = "Book Builder"
STATE = ROOT / "dist" / ".menu-chapter"
MIN_WORDS = 2500  # drafts shorter than this were probably cut off

BATCH_COPY = "Batch: copy the NEXT chapter's writing prompt"
BATCH_SAVE = "Batch: save reply to this chapter, then go to the next"
OTHER = [
    BATCH_COPY,
    BATCH_SAVE,
    "Save ChatGPT reply from clipboard (this chapter)",
    "Save ChatGPT reply from clipboard (pick chapter)",
    "Switch to another chapter",
    "Re-copy this chapter's writing prompt",
    "Chapter status (all chapters)",
    "Find missing or broken files",
    "Build PDF and open it",
    "Copy ChatGPT Project instructions",
    "Quit",
]


# ------------------------------------------------------------------ dialogs

def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()


def choose(items: list[str], prompt: str, default: str | None = None) -> str | None:
    d = f" default items {{{q(default)}}}" if default in items else ""
    res = osa(f"choose from list {{{', '.join(q(i) for i in items)}}} with title {q(TITLE)} with prompt {q(prompt)}{d}")
    return None if res in ("", "false") else res


def say(msg: str) -> None:
    osa(f'display dialog {q(msg[:1800])} with title {q(TITLE)} buttons {{"OK"}} default button "OK"')


def confirm(msg: str, yes: str = "Yes") -> bool:
    return osa(f'display dialog {q(msg[:1800])} with title {q(TITLE)} buttons {{"Cancel", {q(yes)}}} '
               f'default button {q(yes)}\nreturn button returned of result') == yes


def copy_text(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def run(*args: str) -> tuple[bool, str]:
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


# ------------------------------------------------------------------ state and checks

def chapters() -> list[dict]:
    return C.parse_outline()[0]


def load_current() -> int:
    try:
        return int(STATE.read_text().strip())
    except (OSError, ValueError):
        return 1


def save_current(n: int) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(str(n))


def name(ch: dict) -> str:
    return C.chat_name(ch["n"], ch["title"])


def next_in_order(n: int) -> int:
    """The item after n in book order (front matter, chapters 1-60, glossary)."""
    order = [c["n"] for c in chapters()]
    i = order.index(n) if n in order else -1
    return order[min(i + 1, len(order) - 1)]


def stem(ch: dict) -> str:
    return C.chapter_path(ch).stem


def review_dir(ch: dict) -> Path:
    return ROOT / "reviews" / ch["part"]["folder"] / stem(ch)


def draft_version(path: Path) -> int:
    return int(path.name[1:].split("-")[0])


def problems(ch: dict, hashes: dict[str, list[str]] | None = None) -> list[str]:
    """Missing or broken files for one chapter. Empty list = fine."""
    issues = []
    if not C.chapter_path(ch).exists():
        issues.append("The chapter's book file is missing (ask Claude to run scaffold).")
    draft = C.latest_draft(ch)
    if not draft:
        return issues
    issues += text_problems(ch, draft.read_text(encoding="utf-8"), hashes)
    v = draft_version(draft)
    if not (draft.parent / f"v{v}-editor-notes.md").exists():
        issues.append("(Minor) No editor notes: ChatGPT left out the === EDITOR NOTES === line.")
    return issues


def text_problems(ch: dict, text: str, hashes: dict[str, list[str]] | None = None) -> list[str]:
    """Problems in one chapter text (a saved draft, or a reply before saving)."""
    issues = []
    body = re.sub(r"\A---.*?\n---\s*\n", "", text, flags=re.S)
    words = len(body.split())
    if not text.startswith("---"):
        issues.append("Header (front matter) is broken or missing.")
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.M)
    if not m:
        issues.append("No title in the header.")
    elif C.slugify(ch["title"], 2) not in C.slugify(m.group(1), 12):
        issues.append(f"Title is \"{m.group(1)}\", which looks like a different chapter.")
    if words < ch.get("min", MIN_WORDS):
        issues.append(f"Only {words:,} words; it was probably cut off. In ChatGPT, type \"continue\", then save the full chapter.")
    last = body.strip().splitlines()[-1].strip() if body.strip() else ""
    if last and not re.search(r"[.!?:)\"'”*|]$", last) and last not in (":::", "---", "***"):
        issues.append(f"Ends mid-sentence (\"…{last[-60:]}\"); probably cut off.")
    openers = len(re.findall(r"^:::\s*\{", body, re.M))
    closers = len(re.findall(r"^:::\s*$", body, re.M))
    if closers > openers:
        issues.append("Box markup was lost (copied by selecting text). Use the copy button under ChatGPT's reply, then save again.")
    elif openers > closers:
        issues.append("A box (:::) is opened but never closed; probably cut off.")
    if re.search(r"\\[*#\-]|&#x", text):
        issues.append("Contains copy glitches (stray \\ or &#x codes).")
    if hashes is not None:
        dup = [s for s in hashes.get(hashlib.md5(body.strip().encode()).hexdigest(), []) if s != stem(ch)]
        if dup:
            issues.append(f"Same text as chapter {dup[0][:2]}; the wrong reply was saved.")
    return issues


def body_hashes() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ch in chapters():
        d = C.latest_draft(ch)
        if d:
            body = re.sub(r"\A---.*?\n---\s*\n", "", d.read_text(encoding="utf-8"), flags=re.S).strip()
            out.setdefault(hashlib.md5(body.encode()).hexdigest(), []).append(stem(ch))
    return out


def check_message(ch: dict, v: str) -> str:
    """What the author pastes to Claude to ask for a check."""
    if C.is_special(ch):
        return f"Check {C.what(ch)} ({C.label(ch)}), draft {v}."
    return f"Check chapter {ch['n']}, draft {v}."


def serious(issues: list[str]) -> list[str]:
    return [i for i in issues if not i.startswith("(Minor)")]


def next_step(ch: dict, hashes: dict | None = None) -> tuple[str, str]:
    """Return (code, button label) for the chapter's next step."""
    meta, _ = C.front_matter(C.chapter_path(ch))
    if meta.get("status") == "approved":
        return "advance", ("Approved ✓ → go to the next section" if C.is_special(ch)
                           else "Chapter approved ✓ → go to the next chapter")
    draft = C.latest_draft(ch)
    if not draft:
        if (ROOT / "prompts" / f"{stem(ch)}-write.md").exists():
            return "save", "Save ChatGPT's reply (copy it in ChatGPT first)"
        if C.research_path(ch).exists() or (C.is_special(ch) and not ch.get("research")):
            return "write", "Copy the writing prompt (same ChatGPT chat)" if C.research_path(ch).exists() \
                else "Copy the writing prompt for ChatGPT (new chat)"
        if (ROOT / "prompts" / f"{stem(ch)}-research.md").exists():
            return "saveresearch", "Save ChatGPT's research reply (copy it in ChatGPT first)"
        return "research", "Copy the research prompt for ChatGPT"
    if serious(problems(ch, hashes)):
        return "fix", f"⚠ Draft v{draft_version(draft)} has problems: see what to fix"
    v = draft_version(draft)
    check = review_dir(ch) / f"v{v}-check.md"
    if not check.exists():
        return "claude", f"Ask Claude to check draft v{v} (copies the message)"
    if "ready to approve" in check.read_text(encoding="utf-8").lower():
        return "approve", f"Approve draft v{v} into the book"
    if (ROOT / "prompts" / f"{stem(ch)}-revise-v{v}.md").exists():
        return "save", f"Save ChatGPT's revised reply as v{v + 1} (copy it in ChatGPT first)"
    return "revise", "Copy the revision prompt for ChatGPT"


# ------------------------------------------------------------------ steps

def save_reply(ch: dict) -> None:
    text = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    if not text.strip():
        say("Your clipboard is empty. In ChatGPT, click the copy button under the reply first.")
        return
    if not confirm(f"Save this as the next draft of {name(ch)}?\n\nIt starts with:\n{text.strip()[:220]}…", "Save"):
        return
    tmp = ROOT / "dist" / "clipboard-reply.md"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    ok, out = run("tools/chapter.py", "save", str(ch["n"]), str(tmp))
    tmp.unlink(missing_ok=True)
    issues = serious(problems(ch, body_hashes())) if ok else []
    if issues:
        say(out + "\n\n⚠ Problems with what was saved:\n- " + "\n- ".join(issues))
    else:
        say(out + "\n\nNext step: ask Claude to check it (press Next step).")


def do_step(code: str, ch: dict) -> int:
    """Run one step. Returns the chapter number to continue with."""
    n = ch["n"]
    if code in ("write", "recopy"):
        ok, out = run("tools/chapter.py", "write", str(n))
        f = ROOT / "prompts" / f"{stem(ch)}-write.md"
        if not ok or not f.exists():
            say(out)
            return n
        copy_text(f.read_text(encoding="utf-8"))
        say(f"Copied the prompt for {name(ch)}.\n\n1. In ChatGPT, open your project and start a NEW chat.\n"
            f"2. Paste (Cmd+V) and send.\n3. If the chat isn't named \"{name(ch)}\", rename it to that.\n"
            "4. When it's finished, click the copy button under the reply, then come back and press Next step.")
    elif code == "save":
        save_reply(ch)
    elif code == "fix":
        issues = problems(ch, body_hashes())
        msg = (f"{name(ch)}, latest draft:\n\n- " + "\n- ".join(issues) +
               f"\n\nTo fix: open the ChatGPT chat named \"{name(ch)}\", get the complete, correct reply "
               "(type \"continue\" if it was cut off), copy it, then press Save. It becomes the next version.")
        if confirm(msg, "Save fixed reply from clipboard"):
            save_reply(ch)
    elif code == "claude":
        v = C.latest_draft(ch).name.split("-")[0]
        msg = check_message(ch, v)
        copy_text(msg)
        say(f"Copied this message for Claude:\n\n\"{msg}\"\n\nPaste it into Claude Code. "
            "When Claude says the check is done, come back and press Next step.")
    elif code == "revise":
        ok, out = run("tools/chapter.py", "revise", str(n))
        files = sorted((ROOT / "prompts").glob(f"{stem(ch)}-revise-*.md"), key=lambda p: p.stat().st_mtime)
        if not ok or not files:
            say(out)
            return n
        copy_text(files[-1].read_text(encoding="utf-8"))
        say(f"Copied the revision prompt for {name(ch)}.\n\nPaste it into the chat named \"{name(ch)}\". "
            "When it's finished, copy the reply and press Next step.")
    elif code == "approve":
        if confirm(f"Put the latest draft of {name(ch)} into the book as approved?", "Approve"):
            ok, out = run("tools/chapter.py", "approve", str(n))
            copy_text(f"Chapter {n} approved. Update continuity and build.")
            say(out + "\n\nCopied a message for Claude to update the continuity notes. Paste it into Claude Code.\n\n"
                "Next step moves you to the next chapter.")
    elif code == "advance":
        return next_in_order(n)
    return n


def status_lines() -> list[str]:
    hashes = body_hashes()
    out = []
    for ch in chapters():
        code, label = next_step(ch, hashes)
        out.append(f"{C.label(ch)}  {ch['title']}  →  {label}")
    return out


def health_report() -> list[str]:
    hashes = body_hashes()
    lines = []
    for ch in chapters():
        for issue in problems(ch, hashes):
            lines.append(f"{C.label(ch)}  {issue}")
    for f in ("agents/chatgpt-writer.md", "agents/chatgpt-project-instructions.md", "research/continuity.md",
              "research/pass-1/index.yml", "book.yml", "references.bib"):
        if not (ROOT / f).exists():
            lines.append(f"Project file missing: {f}")
    return lines


def main() -> None:
    current = load_current()
    last_pick = None
    while True:
        ch = next(c for c in chapters() if c["n"] == current)
        code, label = next_step(ch, body_hashes())
        top = f"▶ Next step for {name(ch)}: {label}"
        default = last_pick if last_pick in (BATCH_COPY, BATCH_SAVE) else top
        pick = choose([top] + OTHER, f"Working on {name(ch)}.", default)
        if not pick or pick == "Quit":
            save_current(current)
            return
        last_pick = pick if pick in (BATCH_COPY, BATCH_SAVE) else None
        if pick == BATCH_COPY:
            nxt = next((c for c in chapters() if c["n"] == current + 1), None)
            if not nxt:
                say("That was the last chapter.")
            else:
                current = nxt["n"]
                do_step("recopy", nxt)
        elif pick == BATCH_SAVE:
            before = C.latest_draft(ch)
            save_reply(ch)
            if C.latest_draft(ch) != before and current < len(chapters()):
                current += 1
        elif pick == top:
            current = do_step(code, ch)
        elif pick.startswith("Save ChatGPT reply from clipboard (this"):
            save_reply(ch)
        elif pick.startswith("Save ChatGPT reply from clipboard (pick"):
            lines = status_lines()
            sel = choose(lines, "Save the clipboard into which chapter?",
                         next((l for l in lines if l.startswith(f"{current:02d}")), None))
            if sel:
                current = int(sel[:2])
                save_reply(next(c for c in chapters() if c["n"] == current))
        elif pick.startswith("Switch"):
            lines = status_lines()
            sel = choose(lines, "Pick a chapter to work on:",
                         next((l for l in lines if l.startswith(f"{current:02d}")), None))
            if sel:
                current = int(sel[:2])
        elif pick.startswith("Re-copy"):
            do_step("recopy", ch)
        elif pick.startswith("Chapter status"):
            choose(status_lines(), "Every chapter and its next step (close when done).")
        elif pick.startswith("Find missing"):
            report = health_report()
            serious_lines = [l for l in report if "(Minor)" not in l]
            if not report:
                say("No missing or broken files found.")
            else:
                choose(serious_lines + [l for l in report if "(Minor)" in l],
                       f"{len(serious_lines)} problem(s) to fix, {len(report) - len(serious_lines)} minor. "
                       "Switch to a chapter to fix it.")
        elif pick.startswith("Build PDF"):
            ok, out = run("tools/build.py", "build", "pdf")
            if ok:
                subprocess.run(["open", str(ROOT / "dist" / "book.pdf")])
            else:
                say("Build failed:\n\n" + out)
        elif pick.startswith("Copy ChatGPT Project"):
            copy_text((ROOT / "agents/chatgpt-project-instructions.md").read_text(encoding="utf-8"))
            say("Copied. Paste it into your ChatGPT Project's Instructions.")
        save_current(current)


if __name__ == "__main__":
    main()
