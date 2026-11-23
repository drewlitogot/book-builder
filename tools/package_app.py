"""Build the Book Builder desktop app, with everything it needs included.

    python tools/package_app.py                 build for this computer
    python tools/package_app.py --target all    build every target
    python tools/package_app.py --target windows-x64 --target linux-x64

Targets: macos-arm64, macos-x64, windows-x64, linux-x64. Any of them can be built on any system.

Each package holds:
- Electron, which shows Book Builder in its own window (desktop/main.js)
- a standalone Python 3.13 (python-build-standalone) with requirements.txt installed
- Pandoc and Typst, at the versions pinned below
- the Book Builder app, and a Sample Book that is copied to your Books folder on first run.

Node.js is not included. It's only needed to build the reader website, and the app says so if it's
missing.

Output goes to dist/packages/: a .zip with "Book Builder.app" for macOS, a .zip for Windows and a
.tar.gz for Linux. Downloads are checked against their published checksums where there are any, and
cached in dist/packages/.cache so later builds work offline. Standard library only; run it with any
Python 3.10 or newer that has pip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbmanage import paths as P  # noqa: E402
from registry import ENGINE_ASSETS  # noqa: E402

APP = P.APP
OUT = APP / "dist" / "packages"
CACHE = OUT / ".cache"
NAME = "Book Builder"

ELECTRON = "45.4.1"
PYTHON = ("3.13.18", "20261110")
PANDOC = "3.14"
TYPST = "0.15.1"

TARGETS = {
    "macos-arm64": {"electron": "darwin-arm64", "py": "aarch64-apple-darwin", "pandoc": "arm64-macOS.zip",
                    "typst": "aarch64-apple-darwin.tar.xz", "wheels": ["macosx_11_0_arm64"]},
    "macos-x64": {"electron": "darwin-x64", "py": "x86_64-apple-darwin", "pandoc": "x86_64-macOS.zip",
                  "typst": "x86_64-apple-darwin.tar.xz", "wheels": ["macosx_10_13_x86_64"]},
    "windows-x64": {"electron": "win32-x64", "py": "x86_64-pc-windows-msvc", "pandoc": "windows-x86_64.zip",
                    "typst": "x86_64-pc-windows-msvc.zip", "wheels": ["win_amd64"]},
    "linux-x64": {"electron": "linux-x64", "py": "x86_64-unknown-linux-gnu", "pandoc": "linux-amd64.tar.gz",
                  "typst": "x86_64-unknown-linux-musl.tar.xz",
                  "wheels": ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"]},
}

# App files a packaged install doesn't need (developer tooling, tests, the source-tree launchers).
SKIP_APP = ("tests/", "run/", "desktop/", "BookBuilder_Manager.", "Build_App_", "tools/package_app.py")

LINUX_LAUNCHER = """#!/bin/sh
# Starts Book Builder. Double-click it (choose Run if asked), or run ./book-builder.sh
HERE="$(cd "$(dirname "$0")" && pwd)"
# Electron's sandbox helper only works when it's owned by root; without that, start without it.
# Book Builder's window only shows pages from its own local server.
if [ "$(stat -c %u "$HERE/chrome-sandbox" 2>/dev/null)" = "0" ] && [ -u "$HERE/chrome-sandbox" ]; then
  exec "$HERE/book-builder" "$@"
fi
exec "$HERE/book-builder" --no-sandbox "$@"
"""

DESKTOP_INSTALLER = """#!/bin/sh
# Adds Book Builder to your applications menu (run once from this folder).
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/book-builder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Book Builder
Comment=Plan, write, build and publish books
Exec="$HERE/book-builder.sh"
Icon=$HERE/resources/bookbuilder/site/public/favicon.svg
Terminal=false
Categories=Office;
EOF
echo "Added Book Builder to your applications menu."
"""

README = """Book Builder {version} ({target})

Start it:
{start}

Book Builder opens in its own window. To use your web browser instead, choose File > Open in
Browser, or set Settings > Preferences > "Open Book Builder in". Everything runs on this computer.
Your books are kept in your Books folder (you can change it in Settings), and the app's own data in
~/.book-builder. The first time it starts, a Sample Book is copied into your Books folder.

Included: Electron {electron}, Python {py}, Pandoc {pandoc} and Typst {typst}, so PDF, EPUB, DOCX and
HTML builds work without installing anything. Building the reader website also needs Node.js
(https://nodejs.org). Git is optional, for Save Work and publishing.

Book Builder is MIT licensed. Electron is MIT, Pandoc is GPL-2.0-or-later and Typst is Apache-2.0;
their licenses are in the runtime/licenses folder inside the app.
"""

START = {
    "macos": "  Double-click \"Book Builder\" (you can drag it into Applications first). It isn't from the App\n"
             "  Store, so the first time macOS may block it: right-click it and choose Open, or allow it in\n"
             "  System Settings > Privacy & Security > Open Anyway.",
    "windows": "  Double-click \"Book Builder.exe\". If Windows SmartScreen appears, choose More info > Run anyway.",
    "linux": "  Double-click book-builder.sh (choose Run if asked), or run ./book-builder.sh in a terminal.\n"
             "  To add it to your applications menu, run ./add-to-menu.sh once.",
}


def host_target() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    system = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    return f"{system}-{arch}"


def download(url: str, name: str | None = None) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / (name or url.rsplit("/", 1)[-1])
    if not dest.exists():
        print(f"  downloading {url}")
        tmp = dest.with_name(dest.name + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "book-builder-packager"})
        with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:  # noqa: S310 (fixed https URLs)
            shutil.copyfileobj(r, f)
        tmp.rename(dest)
    return dest


def verify(archive: Path, sums_url: str, sums_name: str) -> None:
    """Check a download against the release's published SHA-256 list."""
    sums = download(sums_url, sums_name)
    want = next((line.split()[0] for line in sums.read_text().splitlines()
                 if line.strip().endswith(archive.name)), None)
    got = hashlib.sha256(archive.read_bytes()).hexdigest()
    if want != got:
        archive.unlink()
        sys.exit(f"Checksum mismatch for {archive.name}; deleted it. Run the build again.")


def extract(archive: Path, dest: Path) -> None:
    """Extract without letting any entry escape `dest`; keeps symlinks and executable bits."""
    dest.mkdir(parents=True, exist_ok=True)
    top = dest.resolve()
    if archive.suffix != ".zip":
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
        return
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if ".." in Path(info.filename).parts or Path(info.filename).is_absolute():
                sys.exit(f"Unsafe path in {archive.name}: {info.filename}")
            out = dest / info.filename
            mode = info.external_attr >> 16
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISLNK(mode):
                target = z.read(info).decode()
                if Path(target).is_absolute() or not (out.parent / target).resolve().is_relative_to(top):
                    sys.exit(f"Unsafe link in {archive.name}: {info.filename}")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.symlink_to(target)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(out, "wb") as f:
                    shutil.copyfileobj(src, f)
                if mode & 0o111:
                    out.chmod(0o755)


def find_one(root: Path, name: str) -> Path:
    hits = [p for p in root.rglob(name) if p.is_file()]
    if not hits:
        sys.exit(f"{name} not found in the downloaded archive")
    return hits[0]


def site_packages(py_root: Path, windows: bool) -> Path:
    if windows:
        return py_root / "Lib" / "site-packages"
    return py_root / "lib" / f"python{'.'.join(PYTHON[0].split('.')[:2])}" / "site-packages"


def install_requirements(t: dict, target_dir: Path) -> None:
    plats = [a for w in t["wheels"] for a in ("--platform", w)]
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-compile",
           "--only-binary=:all:", "--implementation", "cp", "--python-version", PYTHON[0].rsplit(".", 1)[0],
           *plats, "--target", str(target_dir), "-r", str(APP / "requirements.txt")]
    subprocess.run(cmd, check=True)


def copy_files(files: list[str], dest: Path) -> None:
    for rel in files:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP / rel, out)


def app_files() -> list[str]:
    files = [f for f in P.source_files(APP) if not f.startswith(SKIP_APP)]
    return sorted(set(files + [f for f in ("LICENSE",) if (APP / f).exists()]))


def sample_files() -> list[str]:
    files = [f for f in P.data_files(APP) if f != "LICENSE"]
    for d in ENGINE_ASSETS:
        files += [str(p.relative_to(APP)) for p in sorted((APP / d).rglob("*")) if p.is_file() and p.name != ".DS_Store"]
    return sorted(set(files))


def add_runtime(t: dict, res: Path, work: Path, windows: bool) -> None:
    runtime = res / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "licenses").mkdir(exist_ok=True)
    print("  Python")
    v, tag = PYTHON
    base = f"https://github.com/astral-sh/python-build-standalone/releases/download/{tag}/"
    archive = download(f"{base}cpython-{v}+{tag}-{t['py']}-install_only.tar.gz")
    verify(archive, f"{base}SHA256SUMS", f"python-{tag}-SHA256SUMS")
    extract(archive, runtime)                              # -> runtime/python
    install_requirements(t, site_packages(runtime / "python", windows))

    exe = ".exe" if windows else ""
    print("  Pandoc")
    pdir = work / "_pandoc"
    extract(download(f"https://github.com/jgm/pandoc/releases/download/{PANDOC}/pandoc-{PANDOC}-{t['pandoc']}"), pdir)
    shutil.copy2(find_one(pdir, f"pandoc{exe}"), runtime / "bin" / f"pandoc{exe}")
    for lic in ("COPYING.md", "COPYING.rtf", "COPYRIGHT.txt", "COPYRIGHT.md"):
        for p in pdir.rglob(lic):
            shutil.copy2(p, runtime / "licenses" / f"pandoc-{p.name}")
            break
    print("  Typst")
    tdir = work / "_typst"
    extract(download(f"https://github.com/typst/typst/releases/download/v{TYPST}/typst-{t['typst']}"), tdir)
    shutil.copy2(find_one(tdir, f"typst{exe}"), runtime / "bin" / f"typst{exe}")
    for p in tdir.rglob("LICENSE"):
        shutil.copy2(p, runtime / "licenses" / "typst-LICENSE")
        break
    for d in (pdir, tdir):
        shutil.rmtree(d)
    if not windows:
        for b in (runtime / "bin").iterdir():
            b.chmod(0o755)


def build(target: str, version: str) -> Path:
    t = TARGETS[target]
    system = target.split("-")[0]
    windows = system == "windows"
    work = OUT / f"work-{target}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"\n== {target}")

    print("  Electron")
    edir = work / "_electron"
    ebase = f"https://github.com/electron/electron/releases/download/v{ELECTRON}/"
    archive = download(f"{ebase}electron-v{ELECTRON}-{t['electron']}.zip")
    verify(archive, f"{ebase}SHASUMS256.txt", f"electron-{ELECTRON}-SHASUMS256.txt")
    extract(archive, edir)
    electron_license = (edir / "LICENSE").read_bytes()

    if system == "macos":
        root = work / f"{NAME}.app"
        (edir / "Electron.app").rename(root)
        shutil.rmtree(edir)
        res = root / "Contents" / "Resources"
        plist_path = root / "Contents" / "Info.plist"
        plist = plistlib.loads(plist_path.read_bytes())
        plist.update({"CFBundleName": NAME, "CFBundleDisplayName": NAME,
                      "CFBundleIdentifier": "io.github.drewlitogot.bookbuilder",
                      "CFBundleShortVersionString": version.split("-")[0], "CFBundleVersion": version})
        plist_path.write_bytes(plistlib.dumps(plist))
    else:
        root = work / NAME
        edir.rename(root)
        res = root / "resources"
        if windows:
            (root / "electron.exe").rename(root / f"{NAME}.exe")
        else:
            (root / "electron").rename(root / "book-builder")
    (res / "default_app.asar").unlink(missing_ok=True)
    (res / "runtime" / "licenses").mkdir(parents=True)
    (res / "runtime" / "licenses" / "electron-LICENSE").write_bytes(electron_license)

    add_runtime(t, res, work, windows)

    print("  App and Sample Book")
    shell = res / "app"
    shell.mkdir()
    shutil.copy2(APP / "desktop" / "main.js", shell / "main.js")
    pkg = json.loads((APP / "desktop" / "package.json").read_text())
    pkg["version"] = version
    (shell / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
    copy_files(app_files(), res / "bookbuilder")
    copy_files(sample_files(), res / "sample-book")

    if system == "macos":
        if sys.platform == "darwin" and shutil.which("codesign"):
            # Re-sign after adding files. An ad-hoc signature lets Apple silicon Macs run it; it isn't notarized.
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(root)], check=True, capture_output=True)
        (work / "README.txt").write_text(readme(version, target, system))
    elif windows:
        (root / "README.txt").write_text(readme(version, target, system).replace("\n", "\r\n"))
    else:
        for name, text in (("book-builder.sh", LINUX_LAUNCHER), ("add-to-menu.sh", DESKTOP_INSTALLER)):
            (root / name).write_text(text)
            (root / name).chmod(0o755)
        (root / "README.txt").write_text(readme(version, target, system))

    base = OUT / f"BookBuilder-{version}-{target}"
    if system == "linux":
        out = Path(f"{base}.tar.gz")
        with tarfile.open(out, "w:gz") as tf:
            tf.add(root, arcname=NAME)
    elif system == "macos" and shutil.which("ditto"):
        out = Path(f"{base}.zip")              # ditto keeps symlinks, permissions and the signature
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", str(work), str(out)], check=True)
    else:
        out = Path(f"{base}.zip")
        zip_tree(work, out)
    shutil.rmtree(work)
    print(f"  -> {out.relative_to(APP)} ({out.stat().st_size / 1e6:.0f} MB)")
    return out


def zip_tree(src: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            arc = str(p.relative_to(src))
            if p.is_symlink():
                info = zipfile.ZipInfo(arc)
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, os.readlink(p))
            elif p.is_file():
                info = zipfile.ZipInfo.from_file(p, arc)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(p, "rb") as f:
                    z.writestr(info, f.read())


def readme(version: str, target: str, system: str) -> str:
    return README.format(version=version, target=target, start=START[system], electron=ELECTRON, py=PYTHON[0],
                         pandoc=PANDOC, typst=TYPST)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", action="append", choices=[*TARGETS, "all"],
                    help="what to build (repeatable; default: this computer)")
    a = ap.parse_args()
    targets = a.target or [host_target()]
    if "all" in targets:
        targets = list(TARGETS)
    for t in targets:
        if t not in TARGETS:
            sys.exit(f"No package for {t}. Choose one of: {', '.join(TARGETS)}")
    if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode:
        sys.exit("This Python has no pip. Install Python from https://www.python.org and run this again.")
    version = P.version()
    OUT.mkdir(parents=True, exist_ok=True)
    built = [build(t, version) for t in targets]
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in built]
    (OUT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
    print(f"\nDone. Packages are in {OUT}")


if __name__ == "__main__":
    main()
