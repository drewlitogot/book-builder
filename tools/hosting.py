"""Website hosting: profiles, custom domain, and a portable website ZIP with a hosting guide (PDF).

Settings live in the book's website.yml under `hosting:` (other keys and comments are left alone):
    hosting:
      provider: github-pages | netlify | cloudflare-pages | static-server | other
      domain: example.com          # optional custom domain; GitHub Pages gets a CNAME file on publish
      zip_base: /                  # where a website ZIP will be hosted ("/" = domain root, or "/books/x/")
Nothing here publishes anything. The ZIP is built from approved content only, link-checked, and is
never installable as an app update.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import yaml

import website as WS

PROVIDERS = {
    "github-pages": "GitHub Pages (Book Builder publishes for you)",
    "netlify": "Netlify (drag-and-drop or Git)",
    "cloudflare-pages": "Cloudflare Pages",
    "static-server": "Any web server or shared hosting (upload the files)",
    "other": "Other static host",
}
DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def settings() -> dict:
    cfg = WS.load_config()
    h = cfg.get("hosting") or {}
    return {"provider": h.get("provider") if h.get("provider") in PROVIDERS else "github-pages",
            "domain": str(h.get("domain") or ""), "zip_base": str(h.get("zip_base") or "/"),
            "url": cfg.get("url") or "", "repo": cfg.get("repo") or "", "configured": WS.CONFIG.exists()}


def clean_base(b: str) -> str:
    parts = [p for p in str(b or "/").split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise ValueError("The path can't contain . or .. parts.")
    b = "/" + "/".join(parts) + "/"
    b = b.replace("//", "/")
    if not re.fullmatch(r"/([A-Za-z0-9._~-]+/)*", b):
        raise ValueError("The path may only contain letters, numbers, dots, dashes and slashes, like /books/my-book/.")
    return b


def save(data: dict) -> dict:
    """Write the hosting block into website.yml, keeping everything else (including comments) as it is."""
    provider = data.get("provider", "github-pages")
    if provider not in PROVIDERS:
        return {"ok": False, "message": "Unknown hosting provider."}
    domain = str(data.get("domain") or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    if domain and not DOMAIN.match(domain):
        return {"ok": False, "message": f"“{domain}” doesn't look like a domain name (for example books.example.com)."}
    try:
        zip_base = clean_base(data.get("zip_base") or "/")
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    text = WS.CONFIG.read_text(encoding="utf-8") if WS.CONFIG.exists() else "# Website settings (Book Builder)\n"
    lines = text.splitlines(keepends=True)
    out, skipping = [], False
    for ln in lines:                                   # drop an existing hosting: block
        if re.match(r"^hosting:", ln):
            skipping = True
            continue
        if skipping and (ln.startswith((" ", "\t")) or not ln.strip()):
            continue
        skipping = False
        out.append(ln)
    text = "".join(out).rstrip() + "\n" + yaml.safe_dump({"hosting": {"provider": provider, "domain": domain, "zip_base": zip_base}},
                                                        sort_keys=False)
    if domain and data.get("use_domain_url"):          # the site's address becomes the custom domain
        new = f"url: https://{domain}/"
        text = re.sub(r"(?m)^url:.*$", new, text, count=1) if re.search(r"(?m)^url:", text) else text + new + "\n"
    yaml.safe_load(text)
    WS.CONFIG.write_text(text, encoding="utf-8")
    return {"ok": True, "settings": settings(),
            "message": "Hosting settings saved." + (" The custom domain is used from the next publish." if domain else "")}


def cname_for_publish() -> str | None:
    s = settings()
    return s["domain"] if s["provider"] == "github-pages" and s["domain"] else None


GUIDE = """---
title: "Hosting your book's website"
subtitle: "{title}"
---

# What's in this ZIP

- `site/`: the complete website, ready to upload. It was built for the address path **`{base}`**{domain_note}.
- `HOSTING-GUIDE.pdf` (this guide) and `README.txt`.
- `website-manifest.json`: every file with its SHA-256 checksum.

The site is plain static files (HTML, CSS, JavaScript, images, fonts). It needs no database or server code,
and it loads no fonts or scripts from other websites.

# Choose where to host it

## Any web server or shared hosting

1. Upload **the contents of `site/`** (not the folder itself) to the folder your host serves at `{base}`.
2. Visit the address in a browser. If pages show without styling, the site was built for a different path:
   make a new ZIP in Book Builder (Website › Website ZIP) with the right path.

## Netlify

1. Sign in at netlify.com and choose **Add new site › Deploy manually**.
2. Drag the `site/` folder onto the page.
3. To use your own domain: **Domain management › Add a domain**, then follow its DNS instructions.
   Build the ZIP with the path `/` for this.

## Cloudflare Pages

1. In the Cloudflare dashboard: **Workers & Pages › Create › Pages › Upload assets**.
2. Upload the `site/` folder and deploy.
3. Add a custom domain under **Custom domains**. Use the path `/`.

## GitHub Pages

Book Builder can publish to GitHub Pages for you (Website › Publish). To do it by hand, put the contents of
`site/` in a repository, then enable **Settings › Pages**. Project sites live at
`https://<user>.github.io/<repository>/`, so build the ZIP with the path `/<repository>/`.

# Custom domains

Point your domain at the host with the DNS records the host gives you (usually a `CNAME` record for a
subdomain such as `books.example.com`). HTTPS certificates are issued automatically by these hosts once
DNS is correct; that can take up to a day.

# Updating the site later

Make a new ZIP in Book Builder and upload it again, replacing all the old files. Only approved chapters,
approved images and approved activities are ever included.

# Checks done when this ZIP was made

- {checks}
- Built {when} from Book Builder {version}.
"""


def make_zip(base: str = "/", downloads: bool = False, log=print) -> dict:
    """Build the public site for `base`, check it, and package it with the hosting guide."""
    import jobs as J  # noqa: PLC0415
    from bbmanage import paths as BP  # noqa: PLC0415
    base = clean_base(base)
    s = settings()
    origin = f"https://{s['domain']}" if s["domain"] else "https://example.com"
    with J.span(0.0, 0.8):
        WS.build(preview=False, downloads=downloads, log=log, base_override=base, origin_override=origin)
    J.report(0.82, "Packaging the website…")
    meta = WS.load_book()["metadata"]
    title = str(meta.get("title") or "Book")
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"
    out_dir = WS.ROOT / "dist" / "website-zip"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{stem}-website-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    files = sorted(p for p in WS.DIST.rglob("*") if p.is_file())
    checks = ["Every page and internal link was checked under the path " + base,
              "No private files (drafts, research, notes, settings) are included"]
    guide_md = GUIDE.format(title=title, base=base, domain_note=f" on **{s['domain']}**" if s["domain"] else "",
                            checks="\n- ".join(checks), when=time.strftime("%Y-%m-%d %H:%M"), version=BP.version())
    work = WS.ROOT / "dist" / "website-zip" / ".work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "HOSTING-GUIDE.md").write_text(guide_md, encoding="utf-8")
    pdf_ok = False
    if shutil.which("pandoc") and shutil.which("typst"):
        r = subprocess.run(["pandoc", str(work / "HOSTING-GUIDE.md"), "-o", str(work / "HOSTING-GUIDE.pdf"),
                            "--pdf-engine=typst", "-V", "papersize=us-letter"], capture_output=True, text=True, timeout=180)
        pdf_ok = r.returncode == 0 and (work / "HOSTING-GUIDE.pdf").exists()
        if not pdf_ok:
            log(f"Hosting guide PDF couldn't be made ({r.stderr.strip()[:200]}); the Markdown guide is included instead.")
    manifest = {"kind": "bookbuilder-website", "installable": False, "title": title, "base": base, "domain": s["domain"],
                "built": time.time(), "files": {}}
    with zipfile.ZipFile(dest.with_suffix(".partial"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            rel = f.relative_to(WS.DIST).as_posix()
            manifest["files"][rel] = hashlib.sha256(f.read_bytes()).hexdigest()
            z.write(f, "site/" + rel)
        z.write(work / "HOSTING-GUIDE.md", "HOSTING-GUIDE.md")
        if pdf_ok:
            z.write(work / "HOSTING-GUIDE.pdf", "HOSTING-GUIDE.pdf")
        z.writestr("README.txt", f"{title}: website files.\nUpload the CONTENTS of site/ to your host at {base}.\n"
                                 f"Full instructions: HOSTING-GUIDE.{'pdf' if pdf_ok else 'md'}\n")
        z.writestr("website-manifest.json", json.dumps(manifest, indent=1))
    dest.with_suffix(".partial").replace(dest)
    shutil.rmtree(work, ignore_errors=True)
    return {"ok": True, "path": str(dest), "name": dest.name, "files": len(files), "base": base, "guide_pdf": pdf_ok,
            "bytes": dest.stat().st_size}
