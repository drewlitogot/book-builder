"""Run the Python test suite and write per-test results as JSON (invoked by qa.py in a subprocess).

Usage: python -m bbmanage.qarunner <tests dir> <output.json>
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import unittest


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.records, self._t = [], {}

    def startTest(self, test):
        self._t[test.id()] = time.time()
        super().startTest(test)

    def _rec(self, test, outcome, detail=""):
        self.records.append({"id": test.id(), "outcome": outcome, "seconds": round(time.time() - self._t.get(test.id(), time.time()), 3),
                             "detail": detail[-4000:]})

    def addSuccess(self, test):
        super().addSuccess(test); self._rec(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err); self._rec(test, "failed", "".join(traceback.format_exception(*err)))

    def addError(self, test, err):
        super().addError(test, err); self._rec(test, "error", "".join(traceback.format_exception(*err)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._rec(test, "skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self._rec(test, "expected-failure")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self._rec(test, "unexpected-success")


def main() -> int:
    tests_dir, out = sys.argv[1], sys.argv[2]
    suite = unittest.defaultTestLoader.discover(tests_dir, top_level_dir=tests_dir)
    runner = unittest.TextTestRunner(resultclass=Recorder, verbosity=1, stream=sys.stdout)
    start = time.time()
    result = runner.run(suite)
    load_errors = [r for r in result.records if r["id"].startswith("unittest.loader")]
    data = {"started": start, "seconds": round(time.time() - start, 2), "tests": result.records,
            "summary": {k: sum(1 for r in result.records if r["outcome"] == k)
                        for k in ("passed", "failed", "error", "skipped", "expected-failure", "unexpected-success")},
            "load_errors": len(load_errors)}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
