"""Image Studio routes (book design module). Registered through routes.py."""
from __future__ import annotations

import base64
import time

import chapter as C
import images as IM
import routes

ROOT = C.ROOT


def _copy(text: str) -> None:
    import platformio  # noqa: PLC0415
    platformio.copy(text)


@routes.get("/api/images")
def list_images(qs: dict) -> dict:
    recs = IM.records()
    for r in recs:
        r["problems"] = IM.approval_problems(r) if r["status"] != "approved" else []
        r["checklist"] = IM.checklist(r["kind"])
        r["markdown"] = IM.markdown(r)
    return {"images": recs, "kinds": IM.KINDS, "statuses": IM.STATUSES}


@routes.post("/api/images/plan-prompt")
def plan_prompt(data: dict) -> dict:
    text = IM.plan_prompt()
    _copy(text)
    return {"ok": True, "chars": len(text), "message": f"Copied the book-wide visual plan prompt ({len(text):,} characters)."}


@routes.post("/api/images/chapter-prompt")
def chapter_prompt(data: dict) -> dict:
    if not str(data.get("chapter", "")).isdigit():
        return {"ok": False, "message": "Choose a chapter."}
    r = IM.chapter_prompt(int(data["chapter"]), data.get("selection") or None)
    _copy(r["text"])
    return {"ok": True, "omitted": r["omitted"], "message": f"Copied the image review prompt for chapter {r['chapter']}"
            + (f" (left out for length: {'; '.join(r['omitted'])})." if r["omitted"] else ".")}


@routes.post("/api/images/import-proposals")
def import_proposals(data: dict) -> dict:
    import platformio  # noqa: PLC0415
    try:
        props = IM.parse_proposals(data.get("text") or platformio.paste())
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    added = IM.add(props, data.get("origin", "AI proposal"))
    return {"ok": True, "added": len(added), "message": f"Added {len(added)} proposed image(s). Review them before making them."}


@routes.post("/api/images/add")
def add(data: dict) -> dict:
    return {"ok": True, "image": IM.add([data], "added by hand")[0]}


@routes.post("/api/images/update")
def update(data: dict) -> dict:
    return {"ok": True, "image": IM.update(data["id"], data)}


@routes.post("/api/images/upload")
def upload(data: dict) -> dict:
    try:
        rec = IM.add_version(data["id"], base64.b64decode(data["data"]), data.get("name", "image"), data.get("source", "upload"))
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "image": rec, "message": "Image added. Review it before approving."}


@routes.post("/api/images/approve")
def approve(data: dict) -> dict:
    return IM.approve(data["id"], data.get("approved", True) is not False)


@routes.post("/api/images/delete")
def delete(data: dict) -> dict:
    return IM.delete(data["id"]) if data.get("confirm") is True else {"ok": False, "message": "Needs confirmation."}


@routes.post("/api/images/pack")
def pack(data: dict) -> dict:
    dest = ROOT / "dist" / "image-requests" / f"image-request-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    try:
        r = IM.generation_pack(data.get("ids") or [], dest)
    except (ValueError, KeyError) as e:
        return {"ok": False, "message": str(e)}
    return {**r, "download": f"/api/images/download?f=image-requests/{dest.name}"}


@routes.post("/api/images/import-return")
def import_return(data: dict) -> dict:
    tmp = ROOT / "dist" / "image-returns" / f"return-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(base64.b64decode(data["data"]))
    try:
        return IM.import_return(tmp)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Couldn't import that ZIP: {e}"}


@routes.post("/api/images/export")
def export(data: dict) -> dict:
    dest = ROOT / "dist" / "image-exports" / f"approved-images-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    r = IM.export_approved(dest)
    return {**r, "download": f"/api/images/download?f=image-exports/{dest.name}"}


@routes.get("/api/images/download")
def download(qs: dict) -> dict:
    f = qs.get("f", "")
    if not __import__("re").fullmatch(r"(image-requests|image-exports)/[\w.-]+\.zip", f):
        raise ValueError("bad name")
    return {"__download__": str(ROOT / "dist" / f), "name": f.split("/")[1]}
