#!/usr/bin/env python3
"""Book Builder application manager: the real implementation behind BookBuilder_Manager.cmd / .command.

    python tools/manage.py                  interactive menu
    python tools/manage.py <command> [...]  one operation (see `python tools/manage.py help`)

Commands: install, launch, update <zip>, qa [--force] [--zip], backup-source, restore-source [zip],
status, backup-data [--private], restore-data [zip], logs [--export], handoff [--module ID] [--task TEXT]
[--manuscript], revision [--json], inspect-update <zip>, make-update ...

Standard library only. Confirmations are typed words (APPLY, RESTORE); nothing destructive happens
without them. Exit code 0 = success, 1 = failure, 2 = cancelled or bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbmanage import backups as B  # noqa: E402
from bbmanage import handoff as H  # noqa: E402
from bbmanage import packages as PK  # noqa: E402
from bbmanage import paths as P  # noqa: E402
from bbmanage import qa as Q  # noqa: E402
from bbmanage import revision as RV  # noqa: E402

MIN_PY = (3, 10)
WIN = os.name == "nt"
VENV_PY = P.APP / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
INTERACTIVE = sys.stdin.isatty()


def say(msg: str = "") -> None:
    print(msg, flush=True)


def ask(prompt: str) -> str:
    if not INTERACTIVE:
        return ""
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def app_python() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def log_line(msg: str) -> None:
    P.LOGS.mkdir(parents=True, exist_ok=True)
    with open(P.LOGS / "manager.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def pick(kind: str, given: str | None) -> Path | None:
    if given:
        return Path(given.strip().strip('"')).expanduser()
    items = B.list_backups(kind)
    if not items:
        say(f"No {kind} backups in {P.BACKUPS / kind}.")
        return None
    for i, b in enumerate(items[:15], 1):
        extra = f"rev {RV.short(b['revision'])}" if b.get("revision") else (b.get("book") or "")
        say(f"  [{i}] {b['name']}  ({b['files']} files, {b['bytes'] // 1024} KB, {extra})")
    choice = ask("Number of the backup to restore (or a full path, Enter to cancel): ")
    if not choice:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(items):
        return Path(items[int(choice) - 1]["path"])
    return Path(choice.strip('"')).expanduser()


# ------------------------------------------------------------------ 1 install
def cmd_install(a) -> int:
    say(f"Book Builder {P.version()} · {P.APP}")
    if sys.version_info < MIN_PY:
        say(f"Python {sys.version.split()[0]} is too old: Book Builder needs {MIN_PY[0]}.{MIN_PY[1]} or newer.")
        say("Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH' on Windows), then run Install again.")
        return 1
    say(f"Python {sys.version.split()[0]}: OK")
    ok = True
    if not VENV_PY.exists():
        say("Creating the app's own Python environment (.venv inside the Book Builder folder)…")
        r = subprocess.run([sys.executable, "-m", "venv", str(P.APP / ".venv")])
        if r.returncode or not VENV_PY.exists():
            say("Couldn't create .venv. On Linux install the python3-venv package; elsewhere reinstall Python.")
            return 1
    else:
        r = subprocess.run([str(VENV_PY), "-c", "import sys"], capture_output=True)
        if r.returncode:
            say("The .venv is broken (Python was probably moved or upgraded).")
            if a.yes or ask("Rebuild it? Type YES: ") == "YES":
                shutil.rmtree(P.APP / ".venv")
                return cmd_install(a)
            return 1
    say(".venv: OK")
    missing = subprocess.run([str(VENV_PY), "-c", "import yaml, jsonschema, segno, PIL"], capture_output=True).returncode
    if missing:
        say("Python packages from requirements.txt are missing. Installing them downloads from PyPI into .venv only.")
        if a.yes or not INTERACTIVE or ask("Install now? Type YES: ") == "YES":
            r = subprocess.run([str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "-r",
                                str(P.APP / "requirements.txt")])
            if r.returncode:
                say("pip failed. Check your internet connection, then run Install again.")
                return 1
        else:
            say("Skipped. Book Builder won't start until they're installed.")
            ok = False
    say("Python packages: OK" if ok else "Python packages: NOT INSTALLED")
    tools = {"pandoc": "needed to build the book (https://pandoc.org/installing.html)",
             "typst": "needed for PDF builds (https://github.com/typst/typst/releases)",
             "node": "only for the website and its tests (https://nodejs.org/)",
             "git": "for Save Work and publishing (https://git-scm.com/downloads)"}
    for t, why in tools.items():
        say(f"{t}: {'found' if shutil.which(t) else 'not found, ' + why}")
    P.ensure_dirs()
    sys.path.insert(0, str(P.APP / "tools"))
    try:
        import registry as REG  # noqa: PLC0415  (needs yaml, so only after packages are in)
        REG.ensure(P.APP)
        say(f"App data: {P.HOME} (Library and settings initialised; existing books untouched)")
    except ImportError:
        say(f"App data folder ready: {P.HOME}")
    say("Book data is plain files (no database), so there is no database to create or migrate.")
    log_line(f"install ok={ok}")
    return 0 if ok else 1


# ------------------------------------------------------------------ 2 launch
def cmd_launch(a) -> int:
    running = PK.server_running()
    if running:
        url = f"http://127.0.0.1:{running[0]}/"
        say(f"Book Builder is already running at {url}")
        if not a.no_open:
            webbrowser.open(url)
        return 0
    py = app_python()
    if py == sys.executable and not VENV_PY.exists():
        say("Note: .venv not found; using this Python. Run Install (option 1) if the app fails to start.")
    P.LOGS.mkdir(parents=True, exist_ok=True)
    logf = P.LOGS / f"server-{time.strftime('%Y%m%d')}.log"
    args = [py, "-u", str(P.APP / "tools" / "webapp.py")] + (["--no-open"] if a.no_open else [])
    say(f"Starting Book Builder… (log: {logf})")
    with open(logf, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        proc = subprocess.Popen(args, cwd=P.APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        started = time.time()
        try:
            for line in proc.stdout:
                lf.write(line); lf.flush()
                sys.stdout.write(line); sys.stdout.flush()
            proc.wait()
        except KeyboardInterrupt:
            say("\nStopping Book Builder…")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            log_line("launch stopped by user")
            return 0
    if proc.returncode and time.time() - started < 10:
        say(f"Book Builder stopped right after starting (exit code {proc.returncode}). The last lines of the log are above.")
        say("Try option 1 (Install) to repair the environment, or option 10 for diagnostics.")
        return 1
    return 0 if proc.returncode in (0, None) else 1


# ------------------------------------------------------------------ 3 update
def show_plan(plan: dict) -> None:
    m = plan["manifest"]
    say(f"\nUpdate: {m['title']}  (package {m['package_id']}{', assignment ' + m['assignment_id'] if m.get('assignment_id') else ''})")
    if m.get("description"):
        say(f"  {m['description']}")
    say(f"  Base revision {RV.short(m['base_revision'])} matches this installation.")
    c = plan["counts"]
    say(f"  {c['add']} added, {c['replace']} replaced, {c['delete']} deleted (application source only; books are not touched):")
    for op in plan["operations"]:
        say(f"    {op['op']:<8} {op['path']}")


def cmd_update(a) -> int:
    z = a.zip or ask("Path of the update ZIP (drag it here): ")
    if not z:
        return 2
    z = Path(z.strip().strip('"')).expanduser()
    try:
        plan = PK.inspect(z)
    except (PK.PackageError, OSError) as e:
        say(f"Rejected: {e}")
        log_line(f"update rejected {z.name}: {e}")
        return 1
    show_plan(plan)
    if a.inspect_only:
        return 0
    word = a.confirm or ask("\nThis stops nothing by itself: quit Book Builder first. Type APPLY to install: ")
    if word != "APPLY":
        say("Cancelled. Nothing changed.")
        return 2
    try:
        r = PK.apply(z, confirm="APPLY", data_backup=not a.no_data_backup)
    except (PK.PackageError, OSError) as e:
        say(f"Update not applied: {e}")
        log_line(f"update failed {z.name}: {e}")
        return 1
    say(f"Applied. Source revision {RV.short(r['from'])} → {RV.short(r['to'])}.")
    say(f"Backups first: {r['source_backup']}" + (f"\n               {r['data_backup']}" if r.get("data_backup") else ""))
    for p_ in r["checks"]["problems"]:
        say(f"  CHECK FAILED: {p_}")
    say(r["checks"]["note"])
    log_line(f"update applied {r['package_id']} {r['from'][:12]}->{r['to'][:12]} checks_ok={r['checks']['ok']}")
    if INTERACTIVE and ask("Run the QA tests now? Type YES: ") == "YES":
        return cmd_qa(argparse.Namespace(force=True, zip=False, no_site=False))
    return 0 if r["ok"] else 1


# ------------------------------------------------------------------ 4 QA
def cmd_qa(a) -> int:
    say("Running the local test suites in an isolated data folder…")
    r = Q.run(force=a.force, python=app_python(), include_site=not getattr(a, "no_site", False))
    if r.get("reused"):
        say(f"This source revision ({RV.short(r['revision'])}) already passed QA on "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['finished']))}. Use --force to run again.")
    for s in r["suites"]:
        sm = s.get("summary", {})
        say(f"  {s['name']}: {s['status'].upper()}  passed {sm.get('passed', 0)}, failed {sm.get('failed', 0)}, "
            f"errors {sm.get('error', 0)}, skipped {sm.get('skipped', 0)}" + (f"  ({s.get('detail')})" if s.get("detail") else ""))
        for t in s.get("tests", []):
            if t["outcome"] in ("failed", "error"):
                say(f"    ✗ {t['id']}")
    say(f"Result: {r['status'].upper()}  (logs: {r['dir']})")
    if a.zip or (INTERACTIVE and ask("Export an AI QA review ZIP? Type YES: ") == "YES"):
        z = Q.review_zip(r)
        say(f"QA review ZIP: {z['path']}")
    log_line(f"qa {r['status']} rev={r['revision'][:12]} reused={r.get('reused')}")
    return 0 if r["status"] == "passed" else 1


# ------------------------------------------------------------------ 5/6 source backup
def cmd_backup_source(a) -> int:
    r = B.make_source_backup(label=a.label or "")
    say(f"Source backup: {r['path']}\n  {r['files']} files, revision {RV.short(r['revision'])}. Book data is not included.")
    log_line(f"backup-source {r['path']}")
    return 0


def cmd_restore_source(a) -> int:
    z = pick("source", a.zip)
    if not z:
        return 2
    try:
        m = B.inspect(z, B.SOURCE_KIND)
    except (ValueError, OSError, Exception) as e:  # noqa: BLE001
        say(f"Can't use this backup: {e}")
        return 1
    cur = RV.current()
    removed = sorted(set(cur["inventory"]) - set(m["files"]))
    changed = sorted(p for p in m["files"] if cur["inventory"].get(p) != m["files"][p])
    say(f"Backup revision {RV.short(m['revision'])} (made {m.get('created')}); current {RV.short(cur['revision'])}.")
    say(f"  {len(changed)} file(s) will be written, {len(removed)} newer file(s) removed. Books are not touched.")
    for p_ in (changed + removed)[:40]:
        say(f"    {'remove ' if p_ in removed else 'restore'} {p_}")
    say("  Book Builder keeps book data as plain files (no database), so there's no schema to downgrade.")
    if PK.server_running():
        say("Quit Book Builder first: its source can't be replaced while it runs.")
        return 1
    word = a.confirm or ask("Type RESTORE to continue: ")
    if word != "RESTORE":
        say("Cancelled. Nothing changed.")
        return 2
    r = B.restore_source(z, confirm="RESTORE")
    say(("Restored." if r["ok"] else "Restored, but the revision doesn't match!") + f" Current revision {RV.short(r['revision'])}.")
    say(f"The source before the restore is saved in {r['pre_restore_backup']}")
    log_line(f"restore-source {z.name} ok={r['ok']}")
    return 0 if r["ok"] else 1


# ------------------------------------------------------------------ 7 status
def cmd_status(a) -> int:
    cur = RV.current()
    qa = Q.history()
    st = PK.state()
    running = PK.server_running()
    info = {
        "version": P.version(), "revision": cur["revision"], "source_files": cur["files"],
        "python": sys.version.split()[0], "os": platform.platform(),
        "venv": "ok" if VENV_PY.exists() else "missing (run Install)",
        "install_dir": str(P.APP), "user_data_dir": str(P.HOME), "home_project": str(P.APP),
        "database": "none: books are plain files (book.yml, Markdown); app data is JSON in the user data dir",
        "server": f"running on port {running[0]}" if running else "not running",
        "last_qa": (f"{qa[-1]['status']} for {RV.short(qa[-1]['revision'])} at {time.strftime('%Y-%m-%d %H:%M', time.localtime(qa[-1]['finished']))}"
                    + (" (current revision)" if qa[-1]["revision"] == cur["revision"] else " (older revision)")) if qa else "never run",
        "source_backups": len(B.list_backups("source")), "data_backups": len(B.list_backups("data")),
        "last_update": (st.get("updates") or [{}])[-1].get("title", "none"),
        "update_ready": "quit Book Builder before updating" if running else "ready (server stopped)",
    }
    if a.json:
        print(json.dumps(info, indent=1))
    else:
        width = max(map(len, info))
        for k, v in info.items():
            say(f"  {k.replace('_', ' '):<{width}}  {v}")
    return 0


# ------------------------------------------------------------------ 8/9 data backup
def cmd_backup_data(a) -> int:
    project = Path(a.project).expanduser().resolve() if a.project else P.APP
    r = B.make_data_backup(project, include_private=a.private, label=a.label or "")
    say(f"Book data backup: {r['path']}\n  {r['files']} files for “{r['book']}”, plus the Library and settings.")
    if r["not_included"]:
        say(f"  Not included: {', '.join(r['not_included'])} (private source copies; add --private to include them).")
    log_line(f"backup-data {r['path']}")
    return 0


def cmd_restore_data(a) -> int:
    z = pick("data", a.zip)
    if not z:
        return 2
    project = Path(a.project).expanduser().resolve() if a.project else P.APP
    try:
        m = B.inspect(z, B.DATA_KIND)
    except (ValueError, OSError, Exception) as e:  # noqa: BLE001
        say(f"Can't use this backup: {e}")
        return 1
    files = [p for p in m["files"] if not p.startswith("appdata/")]
    say(f"Backup of “{m.get('book_title')}” made {m.get('created')}: {len(files)} files, into {project}")
    groups = {}
    for f in files:
        groups[f.split("/")[0]] = groups.get(f.split("/")[0], 0) + 1
    for g_, n in sorted(groups.items()):
        say(f"    {g_:<20} {n} file(s)")
    say("  Application source is not touched. A backup of the current book data is made first.")
    word = a.confirm or ask("Type RESTORE to continue: ")
    if word != "RESTORE":
        say("Cancelled. Nothing changed.")
        return 2
    r = B.restore_data(z, project, confirm="RESTORE", restore_appdata=a.appdata)
    say(f"Restored {r['restored']} files; verification {'passed' if r['ok'] else 'FAILED for ' + str(len(r['mismatched'])) + ' file(s)'}.")
    if r["not_in_backup"]:
        say(f"  {len(r['not_in_backup'])} current file(s) weren't in the backup and were left as they are.")
    say(f"Previous book data saved in {r['pre_restore_backup']}")
    log_line(f"restore-data {z.name} ok={r['ok']}")
    return 0 if r["ok"] else 1


# ------------------------------------------------------------------ 10 logs
def cmd_logs(a) -> int:
    logs = sorted(P.LOGS.glob("*.log"), key=lambda p: p.stat().st_mtime) if P.LOGS.exists() else []
    if not logs:
        say(f"No logs yet in {P.LOGS}.")
    for lf in logs[-3:]:
        lines = lf.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        say(f"── {lf.name} (last {len(lines)} lines) ──")
        for line in lines:
            say("  " + Q.sanitize(line))
    errors = [line for lf in logs for line in lf.read_text(encoding="utf-8", errors="replace").splitlines()
              if "Traceback" in line or "Error" in line][-10:]
    if errors:
        say("── recent errors ──")
        for e in errors:
            say("  " + Q.sanitize(e))
    if a.export or (INTERACTIVE and ask("Export a sanitized diagnostics ZIP? Type YES: ") == "YES"):
        import io  # noqa: PLC0415
        import zipfile  # noqa: PLC0415
        dest = P.HOME / "diagnostics" / f"bookbuilder-diagnostics-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        sys_stdout, sys.stdout = sys.stdout, buf
        try:
            cmd_status(argparse.Namespace(json=True))
        finally:
            sys.stdout = sys_stdout
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps({"kind": "bookbuilder-diagnostics", "installable": False,
                                                    "project_id": P.PROJECT_ID}))
            z.writestr("status.json", Q.sanitize(buf.getvalue()))
            z.writestr("environment.json", json.dumps(Q.environment(), indent=1))
            z.writestr("qa-history.json", json.dumps([{k: r[k] for k in ("run_id", "revision", "status", "totals")}
                                                       for r in Q.history()[-10:]], indent=1))
            for lf in logs[-5:]:
                z.writestr(f"logs/{lf.name}", Q.sanitize("\n".join(lf.read_text(encoding="utf-8", errors="replace").splitlines()[-400:])))
            z.writestr("README.md", "Sanitized diagnostics: no manuscripts, passwords, tokens or email addresses.\n")
        say(f"Diagnostics: {dest}")
    return 0


# ------------------------------------------------------------------ 11 handoff
def cmd_handoff(a) -> int:
    mods = H.modules()["modules"]
    module_ids = a.module or []
    if not module_ids and INTERACTIVE and not a.task:
        say("Modules: " + ", ".join(m["id"] for m in mods))
        pickd = ask("Modules to include (comma-separated, Enter for all): ")
        module_ids = [m.strip() for m in pickd.split(",") if m.strip()]
    unknown = [m for m in module_ids if m not in {x["id"] for x in mods}]
    if unknown:
        say(f"Unknown module(s): {', '.join(unknown)}")
        return 2
    task = a.task or ask("Describe the task for the AI (Enter to describe it later in the chat): ")
    include = a.manuscript or (INTERACTIVE and not a.task and ask("Include manuscript chapters? Type YES (default no): ") == "YES")
    r = H.make(task, module_ids or None, include_manuscript=include)
    say(f"Handoff: {r['path']}\n  revision {RV.short(r['revision'])}, {r['files']} source file(s)"
        + (f", {r['skipped']} binary/large file(s) listed but not included" if r["skipped"] else "")
        + ("\n  Includes manuscript chapters (you asked for them)." if include else ""))
    return 0


# ------------------------------------------------------------------ developer commands
def cmd_revision(a) -> int:
    cur = RV.current()
    if a.json:
        print(json.dumps({"revision": cur["revision"], "files": cur["inventory"]}, indent=1, sort_keys=True))
    else:
        say(f"{cur['revision']}  ({cur['files']} source files)")
    return 0


def cmd_make_update(a) -> int:
    if a.base_backup:
        inv, base = PK.inventory_from_backup(Path(a.base_backup))
    elif a.base_inventory:
        data = json.loads(Path(a.base_inventory).read_text(encoding="utf-8"))
        inv, base = data["files"], data["revision"]
        if RV.revision_of(inv) != base:
            say("The base inventory's revision doesn't match its file list.")
            return 1
    else:
        say("Give --base-backup or --base-inventory.")
        return 2
    root = Path(a.root).resolve() if a.root else P.APP
    try:
        r = PK.make(inv, base, root, Path(a.out), a.id, a.title, a.description or "", a.assignment or "",
                    partial=bool(a.base_inventory), deletes=a.delete or [])
    except PK.PackageError as e:
        say(str(e))
        return 1
    say(f"Update package: {r['path']} ({r['operations']} operation(s)), base {RV.short(r['base_revision'])}")
    return 0


MENU = [("1", "Install / First Run", "install"), ("2", "Launch Book Builder", "launch"),
        ("3", "Update Book Builder from ZIP", "update"), ("4", "Run Local QA Tests", "qa"),
        ("5", "Make Source Backup", "backup-source"), ("6", "Restore Source Backup", "restore-source"),
        ("7", "Installation Status", "status"), ("8", "Make Book Data Backup", "backup-data"),
        ("9", "Restore Book Data Backup", "restore-data"), ("10", "View Logs / Diagnostics", "logs"),
        ("11", "Generate AI Development Handoff", "handoff")]


def menu() -> int:
    while True:
        say("\n" + "=" * 43 + "\n" + "BOOK BUILDER".center(43) + "\n" + "Local Application Manager".center(43) + "\n" + "=" * 43 + "\n")
        for k, label, _ in MENU:
            say(f"[{k}] {label}")
            if k == "8":
                say("")
        say("\n[0] Exit\n")
        c = ask("Choose an option: ")
        if c in ("0", "", "q"):
            return 0
        cmd = next((m[2] for m in MENU if m[0] == c), None)
        if not cmd:
            say("Please type a number from the menu.")
            continue
        try:
            code = main([cmd])
        except KeyboardInterrupt:
            code = 2
        say(f"\n(done, exit code {code})")
        ask("Press Enter to return to the menu… ")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="manage.py", description="Book Builder application manager")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("install"); s.add_argument("--yes", action="store_true"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("launch"); s.add_argument("--no-open", action="store_true"); s.set_defaults(fn=cmd_launch)
    for name, insp in (("update", False), ("inspect-update", True)):
        s = sub.add_parser(name); s.add_argument("zip", nargs="?"); s.add_argument("--confirm")
        s.add_argument("--no-data-backup", action="store_true"); s.set_defaults(fn=cmd_update, inspect_only=insp)
    s = sub.add_parser("qa"); s.add_argument("--force", action="store_true"); s.add_argument("--zip", action="store_true")
    s.add_argument("--no-site", action="store_true"); s.set_defaults(fn=cmd_qa)
    s = sub.add_parser("backup-source"); s.add_argument("--label"); s.set_defaults(fn=cmd_backup_source)
    s = sub.add_parser("restore-source"); s.add_argument("zip", nargs="?"); s.add_argument("--confirm"); s.set_defaults(fn=cmd_restore_source)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("backup-data"); s.add_argument("--private", action="store_true"); s.add_argument("--label")
    s.add_argument("--project"); s.set_defaults(fn=cmd_backup_data)
    s = sub.add_parser("restore-data"); s.add_argument("zip", nargs="?"); s.add_argument("--confirm")
    s.add_argument("--project"); s.add_argument("--appdata", action="store_true"); s.set_defaults(fn=cmd_restore_data)
    s = sub.add_parser("logs"); s.add_argument("--export", action="store_true"); s.set_defaults(fn=cmd_logs)
    s = sub.add_parser("handoff"); s.add_argument("--module", action="append"); s.add_argument("--task")
    s.add_argument("--manuscript", action="store_true"); s.set_defaults(fn=cmd_handoff)
    s = sub.add_parser("revision"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_revision)
    s = sub.add_parser("make-update"); s.add_argument("--base-backup"); s.add_argument("--base-inventory")
    s.add_argument("--root"); s.add_argument("--out", required=True); s.add_argument("--id", required=True)
    s.add_argument("--title", required=True); s.add_argument("--description"); s.add_argument("--assignment")
    s.add_argument("--delete", action="append"); s.set_defaults(fn=cmd_make_update)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.cmd:
        return menu()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
