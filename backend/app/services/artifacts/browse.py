import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from .paths import InvalidPath, resolve_inside

_RASTER_IMAGES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_TEXT_LIKE = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/xhtml+xml",
    "application/x-sh",
    "image/svg+xml",
}

SAFE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-cache",
}


def list_dir(root: Path, rel: str, limit: int, offset: int) -> Dict[str, Any]:
    target = resolve_inside(root, rel)
    if not target.is_dir():
        raise InvalidPath("Not a directory")

    items = []
    with os.scandir(target) as it:
        for entry in it:
            try:
                st = entry.stat(follow_symlinks=False)
                if entry.is_symlink():
                    kind = "symlink"
                elif entry.is_dir(follow_symlinks=False):
                    kind = "dir"
                elif entry.is_file(follow_symlinks=False):
                    kind = "file"
                else:
                    continue
            except OSError:
                continue
            items.append(
                (
                    kind,
                    entry.name,
                    st.st_size if kind == "file" else None,
                    int(st.st_mtime),
                )
            )

    items.sort(key=lambda x: (x[0] != "dir", x[1].lower()))

    base = target.relative_to(root).as_posix()
    base = "" if base == "." else base

    page = items[offset : offset + limit]
    return {
        "path": base,
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "name": name,
                "path": f"{base}/{name}" if base else name,
                "type": kind,
                "size": size,
                "mtime": mtime,
            }
            for kind, name, size, mtime in page
        ],
    }


def _looks_like_text(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(4096)
    except OSError:
        return False
    return b"\x00" not in chunk


def describe_file(path: Path, download: bool) -> Tuple[str, str]:
    if download:
        return "application/octet-stream", "attachment"

    guessed, _ = mimetypes.guess_type(path.name)
    if guessed in _RASTER_IMAGES:
        return guessed, "inline"
    if guessed is None:
        if _looks_like_text(path):
            return "text/plain; charset=utf-8", "inline"
    elif guessed.startswith("text/") or guessed in _TEXT_LIKE:
        return "text/plain; charset=utf-8", "inline"
    return "application/octet-stream", "attachment"
