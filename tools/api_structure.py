"""Book structure editor and per-project publishing switch (book management module). Registered via routes.py."""
from __future__ import annotations

import json

import chapter as C
import registry as REG
import routes
import structure as ST

ROOT = C.ROOT


@routes.get("/api/structure")
def get_structure(qs: dict) -> dict:
    return ST.current()


@routes.post("/api/structure/save")
def save_structure(data: dict) -> dict:
    return ST.save(data.get("parts") or [])


@routes.get("/api/project")
def project_info(qs: dict) -> dict:
    ok, why = REG.publishing_enabled(ROOT)
    pf = REG.project_file(ROOT)
    return {"legacy": not pf, "project": pf, "publishing": ok, "publishingNote": why}


@routes.post("/api/projects/publishing")
def set_publishing(data: dict) -> dict:
    pf = REG.project_file(ROOT)
    if not pf:
        return {"ok": False, "message": "This book uses its existing website settings (website.yml); there's no switch to change."}
    pf.setdefault("publishing", {})["enabled"] = data.get("enabled") is True
    (ROOT / REG.PROJECT_FILE).write_text(json.dumps(pf, indent=1), encoding="utf-8")
    return {"ok": True, "publishing": pf["publishing"]["enabled"],
            "message": "Publishing turned on for this book." if pf["publishing"]["enabled"] else "Publishing turned off for this book."}


# ------------------------------------------------------------------ full-book export / import
import base64  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import bookpack as BK  # noqa: E402


@routes.post("/api/projects/export")
def export_book(data: dict) -> dict:
    root = Path(data.get("path") or ROOT).expanduser().resolve()
    if not any(Path(e["path"]) == root for e in REG.registry()) and root != ROOT:
        return {"ok": False, "message": "Only books in the Library can be exported."}
    r = BK.export(root, ROOT / "dist" / "book-exports", bool(data.get("private")))
    return {**r, "download": f"/api/projects/export-download?f={r['name']}"} if r["ok"] else r


@routes.get("/api/projects/export-download")
def export_download(qs: dict) -> dict:
    name = qs.get("f", "")
    if "/" in name or "\\" in name or not name.endswith(".zip"):
        raise ValueError("bad name")
    return {"__download__": str(ROOT / "dist" / "book-exports" / name), "name": name}


def _staged(token: str) -> Path:
    if not token.isalnum():
        raise ValueError("bad token")
    return REG.HOME / "imports" / f"{token}.zip"


@routes.post("/api/projects/import-book/inspect")
def import_inspect(data: dict) -> dict:
    token = f"{time.strftime('%Y%m%d%H%M%S')}{abs(hash(data.get('name', ''))) % 10**6}"
    dest = _staged(token)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(data["data"]))
    try:
        info = BK.inspect(dest)
    except Exception as e:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        return {"ok": False, "message": f"Can't import this file: {e}"}
    return {"ok": True, "token": token, "info": info,
            "suggested": str(Path(REG.settings()["projectsDir"]).expanduser() / REG.slug(info["title"] or "book"))}


@routes.post("/api/projects/import-book/apply")
def import_apply(data: dict) -> dict:
    z = _staged(str(data.get("token", "")))
    if not z.exists():
        return {"ok": False, "message": "That upload has expired; choose the file again."}
    try:
        r = BK.import_book(z, data.get("folder") or None)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Import failed: {e}"}
    if r.get("ok"):
        z.unlink(missing_ok=True)
    return r


# ------------------------------------------------------------------ website hosting (profiles, domain)
@routes.get("/api/hosting")
def hosting_get(qs: dict) -> dict:
    import hosting as HO  # noqa: PLC0415
    ok, why = REG.publishing_enabled(ROOT)
    return {"settings": HO.settings(), "providers": HO.PROVIDERS, "publishing": ok, "publishingNote": why}


@routes.post("/api/hosting/save")
def hosting_save(data: dict) -> dict:
    import hosting as HO  # noqa: PLC0415
    return HO.save(data)


@routes.get("/api/website-zip")
def website_zip_download(qs: dict) -> dict:
    name = qs.get("f", "")
    if "/" in name or "\\" in name or not name.endswith(".zip"):
        raise ValueError("bad name")
    return {"__download__": str(ROOT / "dist" / "website-zip" / name), "name": name}


# ------------------------------------------------------------------ Send to Kindle (email)
@routes.get("/api/kindle")
def kindle_get(qs: dict) -> dict:
    import kindle as K  # noqa: PLC0415
    return {"settings": K.settings(), "history": K.history()[-10:]}


@routes.post("/api/kindle/save")
def kindle_save(data: dict) -> dict:
    import kindle as K  # noqa: PLC0415
    if data.get("forgetPassword"):
        K.forget_password()
    return K.save(data)


@routes.post("/api/kindle/test")
def kindle_test(data: dict) -> dict:
    import kindle as K  # noqa: PLC0415
    return K.test_connection()


@routes.post("/api/kindle/send")
def kindle_send(data: dict) -> dict:
    import kindle as K  # noqa: PLC0415
    name = str(data.get("file", ""))
    if "/" in name or "\\" in name:
        return {"ok": False, "message": "Bad file name."}
    return K.send(ROOT / "dist" / name, confirm=data.get("confirm") is True)
