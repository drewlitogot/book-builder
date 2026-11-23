"""Book Builder Library, projects, settings, dashboards, fonts and brand routes.

Owned by the Book Management / Book Design modules (see MODULES.json). Registered through routes.py.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import chapter as C
import jobs as J
import menu as M
import routes
from bookmeta import book_meta, save_book_meta

ROOT = C.ROOT
APP = Path(__file__).resolve().parent.parent


def site_info() -> dict:
    return {"configured": (ROOT / "website.yml").exists(), "built": (ROOT / "site" / "dist").exists()}


def app_info() -> dict:
    import registry as REG  # noqa: PLC0415
    return {"app": REG.APP_NAME, "project": str(ROOT), "home": str(APP), "library": REG.library(ROOT),
            "settings": REG.settings(), "templates": {k: {**{kk: v[kk] for kk in ("name", "icon", "desc")}, "parts": [[n, list(c)] for n, c in v["parts"]]}
                                                       for k, v in REG.TEMPLATES.items()},
            "registryPath": str(REG.REGISTRY), "settingsPath": str(REG.SETTINGS)}


def reopen(path: str) -> None:
    """Restart this server on another book project (the page reloads when it's back)."""
    import os  # noqa: PLC0415
    import time as _t  # noqa: PLC0415
    _t.sleep(0.4)
    env = {**os.environ, "BOOK_PROJECT": path}
    args = [sys.executable, str(APP / "tools" / "webapp.py"), "--no-open", "--port", str(routes.ctx.port()), "--exact-port"]
    os.execve(sys.executable, args, env)


def builder_action(data: dict, p: str = "") -> dict:
    import fonts as F  # noqa: PLC0415
    import insights as I  # noqa: PLC0415
    import registry as REG  # noqa: PLC0415
    if p == "/api/projects/open":
        target = Path(data.get("path", "")).expanduser().resolve()
        if not REG.is_project(target):
            return {"ok": False, "message": "That folder isn't a book project (no book.yml)."}
        REG.ensure(target, opened=True)
        if target == ROOT:
            return {"ok": True, "same": True}
        threading.Thread(target=reopen, args=(str(target),), daemon=True).start()
        return {"ok": True, "restarting": True}
    if p == "/api/projects/create":
        import base64  # noqa: PLC0415
        cover = None
        if data.get("cover"):
            cover = (base64.b64decode(data["cover"]["data"]), "." + str(data["cover"].get("name", "x.jpg")).rsplit(".", 1)[-1])
        return REG.create(data.get("title", ""), data.get("template", "custom"), data.get("folder") or None,
                          data.get("author", ""), data.get("subtitle", ""), parts=data.get("parts"), meta=data.get("meta"),
                          brand=data.get("brand"), cover=cover, formats=data.get("formats"))
    if p == "/api/projects/import":
        return REG.import_folder(data.get("folder", ""))
    if p == "/api/projects/archive":
        return {"ok": REG.update(data["path"], archived=bool(data.get("archived", True)))}
    if p == "/api/projects/forget":
        if Path(data["path"]).resolve() in (ROOT, APP):
            return {"ok": False, "message": "The open project and the home project can't be removed from the Library."}
        return {"ok": REG.forget(data["path"]), "message": "Removed from the Library. The folder wasn't touched."}
    if p == "/api/settings/save":
        return {"ok": True, "settings": REG.save_settings(data), "message": "Settings saved."}
    if p == "/api/check/run":
        J.report(0.05, "Running the format check…")
        return {"ok": True, "check": I.run_check()}
    if p == "/api/fonts/install":
        return F.install(data.get("family", ""), ROOT / "assets" / "fonts")
    if p == "/api/brand/save":
        return I.set_typst_brand(data.get("fonts"), data.get("colors"))
    raise KeyError(p)  # unreachable: only the paths bound below are routed here


def builder_get(path: str, qs: dict) -> dict | None:
    import fonts as F  # noqa: PLC0415
    import insights as I  # noqa: PLC0415
    import registry as REG  # noqa: PLC0415
    if path == "/api/app":
        return app_info()
    if path == "/api/insights/dashboard":
        hashes = M.body_hashes()
        chs = [routes.ctx.chapter_summary(c, hashes) for c in M.chapters()]
        return {**I.dashboard(chs, routes.ctx.build_stem(), site_info()), "book": book_meta(), "site": site_info(),
                "memoryStale": C.library_stale()}
    if path == "/api/insights/research":
        return I.research()
    if path == "/api/insights/assets":
        return I.assets()
    if path == "/api/insights/activity":
        return {**I.activity(), "outputs": I.outputs(routes.ctx.build_stem())}
    if path == "/api/insights/brand":
        return {**I.typst_brand(), "installed": I.installed_fonts(), "book": book_meta(),
                "website": (ROOT / "website.yml").read_text(encoding="utf-8") if (ROOT / "website.yml").exists() else None}
    if path == "/api/insights/revisions":
        out = []
        for ch in M.chapters():
            d = C.drafts_dir(ch)
            vs = sorted(d.glob("v*-chapter.md"), key=M.draft_version) if d.exists() else []
            if vs:
                out.append({"n": ch["n"], "title": ch["title"], "versions": len(vs),
                            "latest": vs[-1].stat().st_mtime, "path": routes.ctx.rel(vs[-1])})
        return {"chapters": sorted(out, key=lambda x: -x["latest"])}
    if path == "/api/fonts/catalog":
        return F.catalog(REG.settings()["privacy"].get("fetchFontCatalog", True))
    return None




# POST handlers receive the path too (several share one function).
_action = builder_action


def _bind(path):
    return lambda data: _action(data, path)


for _p in ("/api/projects/open", "/api/projects/create", "/api/projects/import", "/api/projects/archive",
           "/api/projects/forget", "/api/settings/save", "/api/check/run", "/api/fonts/install", "/api/brand/save"):
    routes.POST[_p] = _bind(_p)

for _p in ("/api/app", "/api/insights/dashboard", "/api/insights/research", "/api/insights/assets",
           "/api/insights/activity", "/api/insights/brand", "/api/insights/revisions", "/api/fonts/catalog"):
    routes.GET[_p] = (lambda path: lambda qs: builder_get(path, qs))(_p)
