"""Потоковая упаковка в tar.zst / tar.gz без временных файлов и без буфера в памяти."""

import asyncio
import logging
import os
import queue
import stat
import tarfile
import threading
from contextlib import ExitStack
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator, Literal, Tuple

import zstandard

logger = logging.getLogger(__name__)

Codec = Literal["zst", "gz"]
MEDIA_TYPES = {"zst": "application/zstd", "gz": "application/gzip"}

ZSTD_LEVEL = int(os.getenv("ARCHIVE_ZSTD_LEVEL", "3"))
ZSTD_THREADS = int(os.getenv("ARCHIVE_ZSTD_THREADS", "0"))
CHUNK_SIZE = 256 * 1024
QUEUE_SIZE = 8

Entry = Tuple[Path, str]
EntryFactory = Callable[[], Iterator[Entry]]

_EOF = object()


def iter_regular_files(root: Path, base: Path) -> Iterator[Entry]:
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            full = Path(dirpath, name)
            try:
                if not stat.S_ISREG(full.lstat().st_mode):
                    continue
            except OSError:
                continue
            yield full, full.relative_to(root).as_posix()


def _normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def _put(q: queue.Queue, item: object, cancel: threading.Event) -> None:
    while True:
        if cancel.is_set():
            raise BrokenPipeError("client disconnected")
        try:
            q.put(item, timeout=1)
            return
        except queue.Full:
            continue


def _get(q: queue.Queue, thread: threading.Thread) -> object:
    while True:
        try:
            return q.get(timeout=1)
        except queue.Empty:
            if not thread.is_alive() and q.empty():
                return _EOF


class _ChunkSink:

    def __init__(self, q: queue.Queue, cancel: threading.Event):
        self._q, self._cancel = q, cancel
        self._buf = bytearray()

    def write(self, data) -> int:
        self._buf += data
        if len(self._buf) >= CHUNK_SIZE:
            self._emit()
        return len(data)

    def flush(self) -> None:
        pass

    def _emit(self) -> None:
        if self._buf:
            _put(self._q, bytes(self._buf), self._cancel)
            self._buf.clear()

    def finish(self) -> None:
        self._emit()


def _produce(
    entries: EntryFactory, codec: Codec, q: queue.Queue, cancel: threading.Event
) -> None:
    sink = _ChunkSink(q, cancel)
    try:
        with ExitStack() as stack:
            if codec == "zst":
                cctx = zstandard.ZstdCompressor(level=ZSTD_LEVEL, threads=ZSTD_THREADS)
                out = stack.enter_context(cctx.stream_writer(sink, closefd=False))
                mode = "w|"
            else:
                out, mode = sink, "w|gz"

            with tarfile.open(fileobj=out, mode=mode) as tar:
                for full, arcname in entries():
                    if cancel.is_set():
                        raise BrokenPipeError("client disconnected")
                    try:
                        tar.add(
                            full, arcname=arcname, recursive=False, filter=_normalize
                        )
                    except OSError as e:
                        logger.warning("Couldn't add %s to archive: %s", full, e)
        sink.finish()
        _put(q, _EOF, cancel)
    except BrokenPipeError:
        pass
    except Exception as e:
        try:
            _put(q, e, cancel)
        except BrokenPipeError:
            pass


async def stream_entries(
    entries: EntryFactory, codec: Codec = "zst"
) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    q: queue.Queue = queue.Queue(maxsize=QUEUE_SIZE)
    cancel = threading.Event()
    thread = threading.Thread(
        target=_produce, args=(entries, codec, q, cancel), daemon=True
    )
    thread.start()
    try:
        while True:
            item = await loop.run_in_executor(None, _get, q, thread)
            if item is _EOF:
                break
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        cancel.set()


def stream_directory(
    root: Path, base: Path, codec: Codec = "zst"
) -> AsyncIterator[bytes]:
    return stream_entries(lambda: iter_regular_files(root, base), codec)
