from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.services.artifacts.archive import MEDIA_TYPES, stream_directory
from app.services.artifacts.browse import SAFE_HEADERS, describe_file, list_dir
from app.services.artifacts.manifest import ensure_manifest
from app.services.artifacts.paths import (
    ArtifactError,
    ArtifactNotFound,
    InvalidPath,
    PathForbidden,
    get_artifact_root,
    resolve_inside,
)

router = APIRouter()


@contextmanager
def _errors():
    try:
        yield
    except ArtifactNotFound as e:
        raise HTTPException(404, str(e)) from e
    except PathForbidden as e:
        raise HTTPException(403, str(e)) from e
    except (InvalidPath, ArtifactError) as e:
        raise HTTPException(400, str(e)) from e


def _etag(path: Path) -> str:
    st = path.stat()
    return f'"{st.st_mtime_ns:x}-{st.st_size:x}"'


def _not_modified(request: Request, etag: str, headers: dict) -> Optional[Response]:
    header = request.headers.get("if-none-match")
    if not header:
        return None
    tags = {t.strip().removeprefix("W/") for t in header.split(",")}
    if "*" in tags or etag in tags:
        return Response(status_code=304, headers={**headers, "ETag": etag})
    return None


@router.get("/{artifact_id}/tree")
async def get_tree(
    artifact_id: str,
    path: str = "",
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    with _errors():
        root = await get_artifact_root(artifact_id)
        return await run_in_threadpool(list_dir, root, path, limit, offset)


@router.get("/{artifact_id}/file")
async def get_file(
    request: Request,
    artifact_id: str,
    path: str = Query(..., min_length=1),
    download: bool = False,
):
    with _errors():
        root = await get_artifact_root(artifact_id)
        target = resolve_inside(root, path)
        if not target.is_file():
            raise InvalidPath("Not a regular file")
        media_type, disposition = await run_in_threadpool(
            describe_file, target, download
        )

    etag = _etag(target)
    if (resp := _not_modified(request, etag, SAFE_HEADERS)) is not None:
        return resp
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        content_disposition_type=disposition,
        headers={**SAFE_HEADERS, "ETag": etag},
    )


@router.get("/{artifact_id}/manifest")
async def get_manifest(request: Request, artifact_id: str):
    with _errors():
        root = await get_artifact_root(artifact_id)
        manifest_path = await ensure_manifest(artifact_id, root)

    headers = {"Cache-Control": "private, no-cache"}
    etag = _etag(manifest_path)
    if (resp := _not_modified(request, etag, headers)) is not None:
        return resp
    return FileResponse(
        manifest_path,
        media_type="application/json",
        headers={**headers, "ETag": etag},
    )


@router.get("/{artifact_id}/archive")
async def get_archive(
    artifact_id: str,
    path: str = "",
    fmt: Literal["zst", "gz"] = Query("zst", alias="format"),
):
    with _errors():
        root = await get_artifact_root(artifact_id)
        base = resolve_inside(root, path)
        if not base.is_dir():
            raise InvalidPath("Not a directory")

    return StreamingResponse(
        stream_directory(root, base, fmt),
        media_type=MEDIA_TYPES[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{artifact_id}.tar.{fmt}"',
            "X-Content-Type-Options": "nosniff",
            "X-Accel-Buffering": "no",
        },
    )
