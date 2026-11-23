"""Background jobs with progress, for the Book Manager. Project-agnostic (no book-specific code).

A job runs a function in a thread and keeps its progress, current message, recent log lines and result,
so the browser can show a progress bar by polling /api/jobs/<id>.

How code reports progress:
  - Anywhere (in a job thread or in a command-line tool): `jobs.report(0.4, "Building the PDF")`.
    Fractions are 0..1; None means "busy, amount unknown".
  - `with jobs.span(0.2, 0.8):` maps nested reports into part of the bar, so steps can be composed.
  - A command-line tool started with `jobs.run_cmd` reports by calling the same `jobs.report`; it prints a
    `@@progress <fraction> <message>` line (only when BM_PROGRESS=1 is set, so terminal runs stay clean),
    and `run_cmd` maps those lines into the caller's current span.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable

MARK = "@@progress "
_local = threading.local()
_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()


class Job:
    def __init__(self, title: str):
        self.id = uuid.uuid4().hex[:12]
        self.title = title
        self.progress: float | None = 0.0
        self.message = title
        self.log: list[str] = []
        self.started = time.time()
        self.finished: float | None = None
        self.result: Any = None
        self.error: str | None = None

    @property
    def done(self) -> bool:
        return self.finished is not None

    def update(self, fraction: float | None, message: str | None = None) -> None:
        if fraction is not None:
            self.progress = max(self.progress or 0.0, min(1.0, fraction))  # never moves backwards
        else:
            self.progress = None if not self.progress else self.progress
        if message:
            self.message = message
            self.add_log(message)

    def add_log(self, line: str) -> None:
        self.log.append(line)
        del self.log[:-300]

    def to_dict(self, log_lines: int = 12) -> dict:
        return {"id": self.id, "title": self.title, "progress": self.progress, "message": self.message,
                "log": self.log[-log_lines:], "done": self.done, "elapsed": round((self.finished or time.time()) - self.started, 1),
                "result": self.result if self.done else None, "error": self.error}


def _spans() -> list[tuple[float, float]]:
    if not hasattr(_local, "spans"):
        _local.spans = [(0.0, 1.0)]
    return _local.spans


def _absolute(fraction: float) -> float:
    lo, hi = _spans()[-1]
    return lo + (hi - lo) * max(0.0, min(1.0, fraction))


def current() -> Job | None:
    return getattr(_local, "job", None)


def report(fraction: float | None, message: str = "") -> None:
    """Report progress for the current job, or print a marker for a parent process."""
    absolute = None if fraction is None else _absolute(fraction)
    job = current()
    if job:
        job.update(absolute, message)
    elif os.environ.get("BM_PROGRESS") == "1":
        print(f"{MARK}{'-' if absolute is None else f'{absolute:.4f}'} {message}", flush=True)


@contextmanager
def span(start: float, end: float):
    """Nested reports (0..1) land between start and end of the enclosing span."""
    spans = _spans()
    spans.append((_absolute(start), _absolute(end)))
    try:
        yield
    finally:
        spans.pop()


def steps(items: list, start: float = 0.0, end: float = 1.0):
    """Iterate over items, giving each an equal share of [start, end]. Yields (item, its span)."""
    n = max(1, len(items))
    for i, item in enumerate(items):
        a = start + (end - start) * i / n
        yield item, span(a, start + (end - start) * (i + 1) / n)


@contextmanager
def creep(start: float, end: float, expected_seconds: float, message: str = ""):
    """For one long step with no progress of its own (e.g. typesetting a PDF): move the bar from start
    toward end on a curve that slows down, reaching about two-thirds at the expected time and never end."""
    stop = threading.Event()
    job, spans = current(), list(_spans())
    report(start, message)

    def tick() -> None:
        _local.job, _local.spans = job, spans  # report into the same job and span from this thread
        t0 = time.time()
        while not stop.wait(1.0):
            waited = time.time() - t0
            report(start + (end - start) * waited / (waited + expected_seconds / 2), message)

    th = threading.Thread(target=tick, daemon=True)
    th.start()
    try:
        yield
    finally:
        stop.set()
        th.join()


def run_cmd(args: list[str], cwd: str | os.PathLike | None = None, timeout: int = 600,
            env: dict | None = None) -> tuple[bool, str]:
    """Run a command, streaming its output; progress markers move the current job's bar.
    Returns (ok, output without the markers)."""
    full_env = {**os.environ, **(env or {}), "BM_PROGRESS": "1", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env=full_env, bufsize=1)
    out: list[str] = []
    deadline = time.time() + timeout
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        assert proc.stdout
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith(MARK):
                value, _, message = line[len(MARK):].partition(" ")
                report(None if value == "-" else float(value), message)
                continue
            out.append(line)
            job = current()
            if job and line.strip():
                job.add_log(line)
        proc.wait()
    finally:
        timer.cancel()
        if proc.stdout:
            proc.stdout.close()
    if time.time() > deadline:
        out.append(f"(stopped after {timeout} seconds)")
    return proc.returncode == 0, "\n".join(out).strip()


def start(title: str, fn: Callable[[], Any]) -> Job:
    """Run fn in a background thread as a job."""
    job = Job(title)
    with _lock:
        _jobs[job.id] = job
        for old in [j for j in _jobs.values() if j.done and time.time() - (j.finished or 0) > 3600]:
            _jobs.pop(old.id, None)

    def target() -> None:
        _local.job = job
        _local.spans = [(0.0, 1.0)]
        try:
            job.result = fn()
            job.progress = 1.0
        except Exception as e:  # noqa: BLE001  (shown to the user)
            job.error = str(e) or e.__class__.__name__
        finally:
            job.finished = time.time()

    threading.Thread(target=target, daemon=True, name=f"job-{job.id}").start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def wait(job: Job, seconds: float) -> bool:
    end = time.time() + seconds
    while not job.done and time.time() < end:
        time.sleep(0.02)
    return job.done


if __name__ == "__main__":  # tiny demo: python tools/jobs.py
    for i, (_, s) in enumerate(steps(list(range(4)))):
        with s:
            report(0.5, f"step {i + 1}")
            time.sleep(0.1)
    sys.exit(0)
