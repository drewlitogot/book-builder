"""Send to Kindle by email: explicit opt-in, credentials kept out of the browser, honest delivery status.

- Setup (app-level, in BOOK_BUILDER_HOME/kindle.json): mail server, port, security, user, sender, Kindle
  address. The password is stored in the macOS Keychain when available, otherwise in
  BOOK_BUILDER_HOME/secrets/smtp-password (readable by this user only). It is never sent to the page,
  written to logs, backups, ZIPs or the repository.
- Sending needs `confirm: true` from the person, for one specific file.
- Status is what Book Builder can actually know: "accepted by your mail server" or the server's error.
  Amazon's delivery to the Kindle can't be seen from here, so it is never reported as delivered.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
import time
from email.message import EmailMessage
from pathlib import Path

import registry as REG

CONFIG = REG.HOME / "kindle.json"
SECRET = REG.HOME / "secrets" / "smtp-password"
LOG = REG.HOME / "kindle-log.json"
KEYCHAIN_SERVICE = "Book Builder SMTP"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
KINDLE_FORMATS = {".epub", ".pdf", ".docx"}       # what Amazon's Send to Kindle accepts by email
MAX_BYTES = 50 * 1024 * 1024                      # Amazon's email attachment limit


def settings() -> dict:
    try:
        s = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s = {"enabled": bool(s.get("enabled")), "host": s.get("host", ""), "port": int(s.get("port") or 587),
         "security": s.get("security") if s.get("security") in ("starttls", "ssl") else "starttls",
         "user": s.get("user", ""), "sender": s.get("sender", ""), "kindle": s.get("kindle", "")}
    s["passwordStored"] = _password() is not None
    return s


def _keychain() -> bool:
    return sys.platform == "darwin" and Path("/usr/bin/security").exists() and not os.environ.get("BB_NO_KEYCHAIN")


def _password() -> str | None:
    if _keychain():
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", _account(), "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.rstrip("\n")
    try:
        return SECRET.read_text(encoding="utf-8").rstrip("\n") or None
    except OSError:
        return None


def _account() -> str:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("user") or "smtp"
    except (OSError, ValueError):
        return "smtp"


def _store_password(pw: str) -> str:
    if _keychain():
        r = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", _account(), "-w", pw],
                           capture_output=True, text=True)
        if r.returncode == 0:
            SECRET.unlink(missing_ok=True)
            return "the macOS Keychain"
    SECRET.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRET.parent, 0o700)
    fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(pw)
    return "a file only your user account can read"


def forget_password() -> None:
    if _keychain():
        subprocess.run(["/usr/bin/security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", _account()], capture_output=True)
    SECRET.unlink(missing_ok=True)


def save(data: dict) -> dict:
    host = str(data.get("host", "")).strip()
    if host and not re.fullmatch(r"[A-Za-z0-9.-]{3,253}", host):
        return {"ok": False, "message": "The mail server should look like smtp.example.com."}
    for k in ("sender", "kindle"):
        if data.get(k) and not EMAIL.match(str(data[k]).strip()):
            return {"ok": False, "message": f"“{data[k]}” isn't an email address."}
    if data.get("kindle") and not str(data["kindle"]).strip().lower().endswith(("@kindle.com", "@free.kindle.com")):
        return {"ok": False, "message": "Kindle addresses end in @kindle.com (find yours in Amazon › Devices › your Kindle)."}
    try:
        port = int(data.get("port") or 587)
    except ValueError:
        return {"ok": False, "message": "The port must be a number (587 or 465 usually)."}
    cfg = {"enabled": bool(data.get("enabled")), "host": host, "port": port,
           "security": data.get("security") if data.get("security") in ("starttls", "ssl") else "starttls",
           "user": str(data.get("user", "")).strip(), "sender": str(data.get("sender", "")).strip(),
           "kindle": str(data.get("kindle", "")).strip()}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    where = ""
    if data.get("password"):
        where = _store_password(str(data["password"]))
    return {"ok": True, "settings": settings(),
            "message": "Kindle settings saved" + (f"; the password is kept in {where}." if where else ".")}


def _connect(s: dict, password: str, transport=None):
    if transport:
        return transport(s, password)
    if s["security"] == "ssl":
        server = smtplib.SMTP_SSL(s["host"], s["port"], context=ssl.create_default_context(), timeout=30)
    else:
        server = smtplib.SMTP(s["host"], s["port"], timeout=30)
        server.starttls(context=ssl.create_default_context())
    if s["user"]:
        server.login(s["user"], password)
    return server


def _ready(s: dict) -> str | None:
    if not s["enabled"]:
        return "Send to Kindle by email is off. Turn it on in the setup below first."
    missing = [k for k in ("host", "sender", "kindle") if not s[k]]
    if missing:
        return f"Set up the {', '.join(missing)} first."
    if s["user"] and not s["passwordStored"]:
        return "Store the mail password first."
    return None


def test_connection(transport=None) -> dict:
    s = settings()
    if (why := _ready(s)):
        return {"ok": False, "message": why}
    try:
        server = _connect(s, _password() or "", transport)
        server.quit()
    except (smtplib.SMTPException, OSError) as e:
        return {"ok": False, "message": f"Couldn't sign in to {s['host']}: {_clean(str(e))}"}
    return {"ok": True, "message": f"Signed in to {s['host']}. No email was sent."}


def _clean(msg: str) -> str:
    pw = _password()
    return (msg.replace(pw, "••••") if pw else msg)[:300]


def send(path: Path, confirm: bool = False, transport=None) -> dict:
    s = settings()
    if (why := _ready(s)):
        return {"ok": False, "status": "not-sent", "message": why}
    if not confirm:
        return {"ok": False, "status": "not-sent", "message": "Sending needs your confirmation."}
    if not path.is_file() or path.suffix.lower() not in KINDLE_FORMATS:
        return {"ok": False, "status": "not-sent", "message": "Choose an EPUB, PDF or DOCX file that exists."}
    if path.stat().st_size > MAX_BYTES:
        return {"ok": False, "status": "not-sent", "message": "Amazon accepts attachments up to 50 MB; this file is larger. Use amazon.com/sendtokindle instead."}
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["sender"], s["kindle"], path.stem
    msg.set_content(f"{path.name}, sent from Book Builder.")
    ctype = {".epub": ("application", "epub+zip"), ".pdf": ("application", "pdf"),
             ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")}[path.suffix.lower()]
    msg.add_attachment(path.read_bytes(), maintype=ctype[0], subtype=ctype[1], filename=path.name)
    try:
        server = _connect(s, _password() or "", transport)
        refused = server.send_message(msg)
        server.quit()
    except (smtplib.SMTPException, OSError) as e:
        rec = {"time": time.time(), "file": path.name, "to": s["kindle"], "status": "failed", "error": _clean(str(e))}
        _log(rec)
        return {"ok": False, "status": "failed", "message": f"The mail server didn't accept it: {rec['error']}"}
    status = "refused" if refused else "sent-to-server"
    _log({"time": time.time(), "file": path.name, "bytes": path.stat().st_size, "to": s["kindle"], "status": status})
    return {"ok": not refused, "status": status,
            "message": (f"{path.name} was accepted by {s['host']} for {s['kindle']}. Book Builder can't see Amazon's side: "
                        f"it usually appears in your Kindle library within minutes, if {s['sender']} is on Amazon's "
                        "Approved Personal Document E-mail List.") if not refused else "The mail server refused the Kindle address."}


def _log(rec: dict) -> None:
    try:
        items = json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    items = (items + [rec])[-50:]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(items, indent=1), encoding="utf-8")


def history() -> list[dict]:
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
