"""Brand Studio routes (book design module). Registered through routes.py."""
from __future__ import annotations

import base64

import brand as BR
import routes


@routes.get("/api/brand")
def get_brand(qs: dict) -> dict:
    b = BR.load()
    return {"brand": b, "checks": BR.checks(b["colors"]),
            "tokens": {"colors": {k: v[2] for k, v in BR.COLOR_TOKENS.items()}, "fonts": BR.FONT_TOKENS, "assets": BR.ASSET_SLOTS},
            "installed": {fam: bool(BR.font_files(fam)) for fam in {v for v in b["fonts"].values() if v}}}


@routes.post("/api/brand/tokens")
def save_tokens(data: dict) -> dict:
    r = BR.save(data)
    return {**r, "checks": BR.checks(r["brand"]["colors"])} if r["ok"] else r


@routes.post("/api/brand/contrast")
def contrast(data: dict) -> dict:
    return {"checks": BR.checks({k: v for k, v in (data.get("colors") or {}).items() if BR.HEX.match(str(v))})}


@routes.post("/api/brand/apply")
def apply(data: dict) -> dict:
    targets = [t for t in data.get("targets") or [] if t in ("pdf", "ebook", "website")]
    if not targets:
        return {"ok": False, "message": "Choose at least one output."}
    return BR.apply(targets)


@routes.post("/api/brand/asset")
def asset(data: dict) -> dict:
    return BR.save_asset(data.get("slot", ""), data.get("name", ""), base64.b64decode(data.get("data", "")))


@routes.post("/api/brand/prompt")
def prompt(data: dict) -> dict:
    import platformio  # noqa: PLC0415
    text = BR.strategy_prompt()
    platformio.copy(text)
    return {"ok": True, "message": "Copied a brand strategy prompt. Paste it into ChatGPT or Claude, then copy its whole reply."}


@routes.post("/api/brand/suggestion")
def suggestion(data: dict) -> dict:
    import platformio  # noqa: PLC0415
    text = data.get("text") or platformio.paste()
    try:
        s = BR.parse_suggestion(text)
    except ValueError as e:
        return {"ok": False, "message": f"Couldn't read the reply: {e} Copy the whole reply, including the ```json block."}
    return {"ok": True, "suggestion": s, "checks": BR.checks({**BR.load()["colors"], **s["colors"]}),
            "message": "Suggestion loaded into the form. Review it, then Save."}
