import asyncio
import hashlib
import json
import os
import stat
import weakref
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from starlette.concurrency import run_in_threadpool

from .paths import SHARED_DATA_ROOT

CACHE_DIR = Path(os.getenv("MANIFEST_CACHE_DIR", str(SHARED_DATA_ROOT / ".manifests")))
HASH_WORKERS = int(os.getenv("MANIFEST_HASH_WORKERS", "4"))

Entry = Tuple[str, int, int]

_locks: "weakref.WeakValueDictionary[str, asyncio.Lock]" = weakref.WeakValueDictionary()


def _scan(root: Path) -> Tuple[List[Entry], str]:
    entries: List[Entry] = []
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(dirpath, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            entries.append((rel, st.st_size, st.st_mtime_ns))
    entries.sort()

    h = hashlib.sha256()
    for rel, size, mtime in entries:
        h.update(f"{rel}\0{size}\0{mtime}\n".encode())
    return entries, h.hexdigest()


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _build(root: Path, artifact_id: str, entries: List[Entry], fp: str) -> bytes:
    with ThreadPoolExecutor(max_workers=HASH_WORKERS) as pool:
        digests = list(pool.map(lambda e: _sha256(os.path.join(root, e[0])), entries))

    files = [
        {"path": rel, "size": size, "sha256": digest}
        for (rel, size, _mt), digest in zip(entries, digests)
    ]
    doc = {
        "artifact_id": artifact_id,
        "fingerprint": fp,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_size": sum(f["size"] for f in files),
        "files": files,
    }
    return json.dumps(doc, separators=(",", ":")).encode()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _is_fresh(fp_path: Path, json_path: Path, fp: str) -> bool:
    try:
        return json_path.is_file() and fp_path.read_text() == fp
    except OSError:
        return False


async def ensure_manifest(artifact_id: str, root: Path) -> Path:
    json_path = CACHE_DIR / f"{artifact_id}.json"
    fp_path = CACHE_DIR / f"{artifact_id}.fp"

    entries, fp = await run_in_threadpool(_scan, root)
    if _is_fresh(fp_path, json_path, fp):
        return json_path

    lock = _locks.get(artifact_id)
    if lock is None:
        lock = _locks.setdefault(artifact_id, asyncio.Lock())

    async with lock:
        if _is_fresh(fp_path, json_path, fp):
            return json_path
        data = await run_in_threadpool(_build, root, artifact_id, entries, fp)
        await run_in_threadpool(_write_atomic, json_path, data)
        await run_in_threadpool(_write_atomic, fp_path, fp.encode())
    return json_path
