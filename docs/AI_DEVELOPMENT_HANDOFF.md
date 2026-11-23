# AI development handoff

Option 11 (`python tools/manage.py handoff [--module ID ...] [--task "…"] [--manuscript]`) writes a ZIP to `~/.book-builder/handoffs/` for a new ChatGPT or Claude conversation. The person carries it over; Book Builder calls no AI APIs.

**Contents:**
- `HANDOFF.md`: the task, the rules and the exact source revision
- `source-inventory.json`: every source path and its SHA-256
- `MODULES.json` and the architecture, contract, testing and backup docs
- `source/…`: the selected module's files (default: all text source files), plus `tools/manage.py` and `tools/bbmanage/` so the AI can build its return package
- `manuscript/…`: chapters, **only** with `--manuscript`

Binary and very large files are listed in `SKIPPED_FILES.md`, and their hashes stay in the inventory.

**The AI returns** one update package built on that revision (UPDATE_PACKAGE_CONTRACT.md). If it can run Python:

```
python source/tools/manage.py make-update --base-inventory source-inventory.json --root source --out update.zip --id <id> --title "<title>"
```

Otherwise it returns the changed files in full, and you build the package with the same command.

**You then:**
1. Option 3: inspect the package, check the plan, type APPLY.
2. Option 4: run QA.
3. Option 4's QA review ZIP can go back to the AI as evidence. It is never installable.

## Assignments for parallel agents

Give each agent one module (`--module`) and an `assignment_id` to put in its manifest. Packages are applied one at a time. A package built on an older revision is rejected and must be rebuilt on the new revision; there is no automatic merging.
