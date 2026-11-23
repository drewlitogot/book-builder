"""Composition layer for Book Builder's local web server.

Feature modules register their HTTP handlers here instead of being edited into tools/webapp.py:

    import routes
    @routes.get("/api/thing")            def thing(qs): ...      -> dict
    @routes.post("/api/thing/do")        def do(data): ...       -> dict
    @routes.post("/api/things/*")        prefix match (the longest registered prefix wins)

webapp.py loads the modules listed in FEATURES at startup and calls handle_get / handle_post first.
Modules never import webapp (it runs as __main__); the few webapp helpers they need are provided
through `ctx`, which webapp fills in before loading them. That keeps imports one-directional.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Callable

GET: dict[str, Callable] = {}
POST: dict[str, Callable] = {}
ctx = SimpleNamespace()          # filled by webapp: port(), chapter_summary, build_stem, rel, root, app

# Feature modules served by the web app. Add a module here to plug in its routes.
FEATURES = ["api_library", "api_git", "api_research", "api_structure", "api_brand", "api_images"]


def _register(table: dict, paths: tuple[str, ...]):
    def deco(fn: Callable) -> Callable:
        for p in paths:
            if p in table and table[p] is not fn:
                raise ValueError(f"Route {p} is registered twice")
            table[p] = fn
        return fn
    return deco


def get(*paths: str):
    return _register(GET, paths)


def post(*paths: str):
    return _register(POST, paths)


def find(table: dict, path: str) -> Callable | None:
    if path in table:
        return table[path]
    prefixes = [p for p in table if p.endswith("*") and path.startswith(p[:-1])]
    return table[max(prefixes, key=len)] if prefixes else None


def handle_get(path: str, qs: dict):
    fn = find(GET, path)
    return None if fn is None else fn(qs)


def handle_post(path: str, data: dict):
    fn = find(POST, path)
    return None if fn is None else fn(data)


def load(names: list[str] | None = None) -> None:
    for name in names or FEATURES:
        importlib.import_module(name)
