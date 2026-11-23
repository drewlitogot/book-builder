# Versioning

## API version

`apiVersion` in both files names the Game Package API version: currently **1.1** (1.0 packages still run unchanged; see `whats-new-1.1.md`).

- **Minor API versions** (1.1, 1.2…) only add optional features. A 1.x runtime runs every 1.0 package
  unchanged. New features are declared through `requiredCapabilities`, so an older runtime refuses a
  package that needs something it lacks instead of running it wrongly.
- **Major API versions** (2.0) may change or remove things. The builder states which versions it accepts
  (`SUPPORTED_API` in `tools/games.py`); packages for an unsupported version are rejected with a clear
  message. When 2.0 exists, 1.0 packages keep working until the editor migrates them.
- The JSON Schemas are versioned with the API (`schemas/*.schema.json` describe 1.1 and accept 1.0 packages).

## Package version

`version` in `game.json` uses semantic versioning:

| Change | Bump | Example |
|---|---|---|
| Typo or wording fix | PATCH | 1.0.0 → 1.0.1 |
| New screens, options or feedback; same purpose | MINOR | 1.0.1 → 1.1.0 |
| Different activity, different learning objectives | MAJOR | 1.1.0 → 2.0.0 |

## Updating an installed game

- Keep the same `id` and raise `version`. Import with **Replace or update** ticked.
- The builder refuses a lower version, or the same version with different contents.
- An updated game goes back to **review**. The website keeps showing the old version until the next
  publish; if the site is published before the update is approved, the game is left out until it is.
  The registry keeps a history of replaced versions.
- To make a different activity, use a new `id`. Never reuse a removed game's id for something else.
