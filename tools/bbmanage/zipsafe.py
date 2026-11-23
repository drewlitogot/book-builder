"""Inspect ZIP archives safely before trusting any of their contents. Nothing in an archive is executed."""
from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path

MAX_ENTRIES = 20000
MAX_TOTAL = 2 * 1024 ** 3          # 2 GB uncompressed
MAX_ENTRY = 512 * 1024 ** 2        # 512 MB per file
MAX_RATIO = 200                    # compression ratio that suggests a zip bomb


class UnsafeArchive(Exception):
    pass


def safe_name(name: str) -> bool:
    return bool(name) and not name.startswith("/") and "\\" not in name and not re.match(r"^[A-Za-z]:", name) \
        and ".." not in name.split("/") and "\0" not in name


def check(zpath: Path, max_total: int = MAX_TOTAL) -> list[zipfile.ZipInfo]:
    """Return the archive's file entries, or raise UnsafeArchive with the first problem found."""
    try:
        z = zipfile.ZipFile(zpath)
    except (zipfile.BadZipFile, OSError) as e:
        raise UnsafeArchive(f"Not a readable ZIP file: {e}") from e
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise UnsafeArchive(f"Too many entries ({len(infos)}).")
        seen, total, files = set(), 0, []
        for i in infos:
            if not safe_name(i.filename):
                raise UnsafeArchive(f"Unsafe path in archive: {i.filename!r}")
            if i.flag_bits & 0x1:
                raise UnsafeArchive(f"Encrypted entry: {i.filename}")
            mode = i.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise UnsafeArchive(f"Symbolic link in archive: {i.filename}")
            key = i.filename.rstrip("/").lower()
            if key in seen:
                raise UnsafeArchive(f"Duplicate (or case-colliding) entry: {i.filename}")
            seen.add(key)
            if i.is_dir():
                continue
            if i.file_size > MAX_ENTRY:
                raise UnsafeArchive(f"Entry too large: {i.filename}")
            if i.compress_size and i.file_size / i.compress_size > MAX_RATIO and i.file_size > 1024 ** 2:
                raise UnsafeArchive(f"Suspicious compression ratio: {i.filename}")
            total += i.file_size
            if total > max_total:
                raise UnsafeArchive("Archive is too large when extracted.")
            files.append(i)
        return files


def read(zpath: Path, name: str) -> bytes:
    with zipfile.ZipFile(zpath) as z:
        return z.read(name)
