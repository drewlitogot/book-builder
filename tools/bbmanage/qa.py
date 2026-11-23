"""Local QA: run the real test suites in isolation, keep revision-scoped history, export review ZIPs.

Tests run with BOOK_BUILDER_HOME pointed at a temporary folder, so they never touch the real Library,
settings or backups. (The suites create their own temporary book projects for anything they write.)
A QA review ZIP is evidence only: its package type can never be installed as an update.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import paths as P
from . import revision as RV

QA_KIND = "bookbuilder-qa-review"
REDACT = [(re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16})"), "[REDACTED-TOKEN]"),
          (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
          (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]")]


def sanitize(text: str) -> str:
    for rx, rep in REDACT:
        text = rx.sub(rep, text)
    return text.replace(str(Path.home()), "~")


def history() -> list[dict]:
    runs = []
    for f in sorted(P.QA_DIR.glob("*/*/run.json")) if P.QA_DIR.exists() else []:
        try:
            runs.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(runs, key=lambda r: r.get("finished", 0))


def last_pass(revision: str) -> dict | None:
    return next((r for r in reversed(history()) if r["revision"] == revision and r["status"] == "passed"), None)


def run(force: bool = False, python: str | None = None, include_site: bool = True) -> dict:
    """Run the suites. Skips (and says so) when this exact source revision already passed, unless forced."""
    P.ensure_dirs()
    rev = RV.current()["revision"]
    if not force and (prev := last_pass(rev)):
        return {**prev, "reused": True}
    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = P.QA_DIR / RV.short(rev) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    py = python or sys.executable
    suites = []
    with tempfile.TemporaryDirectory() as iso:
        env = {**os.environ, "BOOK_BUILDER_HOME": iso, "PYTHONPATH": str(P.APP / "tools")}
        env.pop("BOOK_PROJECT", None)
        res_file = out_dir / "python-results.json"
        start = time.time()
        r = subprocess.run([py, "-m", "bbmanage.qarunner", str(P.APP / "tests"), str(res_file)], cwd=P.APP / "tools",
                           env=env, capture_output=True, text=True, timeout=1800)
        (out_dir / "python.log").write_text(sanitize(r.stdout + r.stderr), encoding="utf-8")
        if res_file.exists():
            data = json.loads(res_file.read_text(encoding="utf-8"))
            suites.append({"name": "python-unittest", "status": "passed" if r.returncode == 0 else "failed",
                           "summary": data["summary"], "seconds": data["seconds"], "tests": data["tests"]})
        else:
            suites.append({"name": "python-unittest", "status": "error", "summary": {}, "seconds": round(time.time() - start, 1),
                           "tests": [], "detail": sanitize((r.stderr or r.stdout)[-3000:])})
        site = P.APP / "site"
        if include_site:
            if not (site / "node_modules").exists() or not shutil.which("npx"):
                suites.append({"name": "site-vitest", "status": "unavailable", "summary": {},
                               "detail": "Node dependencies aren't installed (site/node_modules), so the website tests weren't run."})
            else:
                start = time.time()
                r = subprocess.run(["npx", "vitest", "run", "--reporter=json", "--outputFile", str(out_dir / "vitest.json")],
                                   cwd=site, env=env, capture_output=True, text=True, timeout=900)
                (out_dir / "vitest.log").write_text(sanitize(r.stdout + r.stderr), encoding="utf-8")
                summary, tests = {}, []
                try:
                    v = json.loads((out_dir / "vitest.json").read_text(encoding="utf-8"))
                    summary = {"passed": v.get("numPassedTests", 0), "failed": v.get("numFailedTests", 0),
                               "skipped": v.get("numPendingTests", 0) + v.get("numTodoTests", 0)}
                    tests = [{"id": f"{Path(f['name']).name}::{t.get('fullName') or t.get('title')}", "outcome":
                              {"passed": "passed", "failed": "failed"}.get(t.get("status"), "skipped")}
                             for f in v.get("testResults", []) for t in f.get("assertionResults", [])]
                except (OSError, ValueError):
                    pass
                suites.append({"name": "site-vitest", "status": "passed" if r.returncode == 0 else "failed",
                               "summary": summary, "seconds": round(time.time() - start, 1), "tests": tests})
    ran = [s for s in suites if s["status"] != "unavailable"]
    status = "passed" if ran and all(s["status"] == "passed" for s in ran) else "failed"
    record = {"run_id": run_id, "revision": rev, "version": P.version(), "status": status, "finished": time.time(),
              "suites": suites, "dir": str(out_dir),
              "totals": {k: sum(s["summary"].get(k, 0) for s in suites) for k in ("passed", "failed", "error", "skipped")}}
    (out_dir / "run.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return {**record, "reused": False}


def environment() -> dict:
    def ver(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, IndexError):
            return None
    return {"os": platform.platform(), "python": sys.version.split()[0], "machine": platform.machine(),
            "book_builder": P.version(), "pandoc": ver(["pandoc", "--version"]), "typst": ver(["typst", "--version"]),
            "node": ver(["node", "--version"]), "git": ver(["git", "--version"])}


def review_zip(record: dict | None = None, dest_dir: Path | None = None) -> dict:
    """Package the evidence of a QA run (the latest by default). Contains only what actually exists."""
    record = record or (history()[-1] if history() else None)
    if not record:
        return {"ok": False, "message": "No QA run yet. Run the tests first (option 4)."}
    run_dir = Path(record["dir"])
    tests = [dict(t, suite=s["name"]) for s in record["suites"] for t in s.get("tests", [])]
    failing = [t for t in tests if t["outcome"] in ("failed", "error")]
    unavailable = [s for s in record["suites"] if s["status"] in ("unavailable", "error")]
    report = [f"# Book Builder QA report", "", f"- Source revision: `{record['revision']}`", f"- Version: {record['version']}",
              f"- Run: {record['run_id']} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(record['finished']))})",
              f"- Result: **{record['status'].upper()}**", "", "| Suite | Status | Passed | Failed | Errors | Skipped |",
              "|---|---|---|---|---|---|"]
    for s in record["suites"]:
        sm = s.get("summary", {})
        report.append(f"| {s['name']} | {s['status']} | {sm.get('passed', 0)} | {sm.get('failed', 0)} | {sm.get('error', 0)} | {sm.get('skipped', 0)} |")
    report += ["", "Tests ran with an isolated temporary BOOK_BUILDER_HOME. No screenshots were captured by this runner."]
    known = ["# Known issues", ""] + ([f"- `{t['id']}` ({t['outcome']})" for t in failing] or ["- None from this run."]) + \
        [f"- Suite `{s['name']}` {s['status']}: {s.get('detail', '')}" for s in unavailable]
    nxt = ["# Next steps", ""] + (["- Fix the failing tests listed in KNOWN_ISSUES.md, then rerun QA (option 4)."] if failing else
                                   ["- No failures. Any further work should add tests for the module it changes."]) + \
        (["- Install the missing tools for unavailable suites and rerun."] if unavailable else [])
    files = {"QA_REPORT.md": "\n".join(report) + "\n", "KNOWN_ISSUES.md": "\n".join(known) + "\n",
             "NEXT_STEPS.md": "\n".join(nxt) + "\n", "test-results.json": json.dumps(tests, indent=1),
             "environment.json": json.dumps(environment(), indent=1)}
    for log in sorted(run_dir.glob("*.log")):
        files[f"logs/{log.name}"] = sanitize(log.read_text(encoding="utf-8", errors="replace"))
    checks = {n: RV.sha256_bytes(c.encode("utf-8")) for n, c in files.items()}
    manifest = {"schema": 1, "kind": QA_KIND, "package_type": QA_KIND, "installable": False, "project_id": P.PROJECT_ID,
                "revision": record["revision"], "run_id": record["run_id"], "executed": record["finished"],
                "status": record["status"], "totals": record["totals"], "evidence_sha256": checks}
    dest = (dest_dir or P.QA_DIR / "exports") / f"bookbuilder-qa-{RV.short(record['revision'])}-{record['run_id']}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("qa-manifest.json", json.dumps(manifest, indent=1))
        z.writestr("manifest.json", json.dumps({"kind": QA_KIND, "project_id": P.PROJECT_ID}))
        for n, c in files.items():
            z.writestr(n, c)
    return {"ok": True, "path": str(dest), "files": len(files) + 2}
