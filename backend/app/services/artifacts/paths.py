import os
import re
from pathlib import Path

from app.core.app_manager import storage

SHARED_DATA_ROOT = Path(os.getenv("SHARED_DATA_ROOT", "/shared_data"))

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class ArtifactError(Exception):
    """Base error. Route translates it into an HTTP code."""


class ArtifactNotFound(ArtifactError):  # 404
    pass


class InvalidPath(ArtifactError):  # 400
    pass


class PathForbidden(ArtifactError):  # 403
    pass


def validate_artifact_id(artifact_id: str) -> str:
    if not _ID_RE.fullmatch(artifact_id):
        raise InvalidPath("Invalid artifact id")
    return artifact_id


async def get_artifact_root(artifact_id: str) -> Path:
    validate_artifact_id(artifact_id)

    info = await storage.get_scan_status(artifact_id)
    folder = info.get("folder_path") if info else None
    if not folder:
        raise ArtifactNotFound(f"Artifact {artifact_id} not found")

    base = SHARED_DATA_ROOT.resolve()
    root = (base / folder).resolve()
    if root == base or not root.is_relative_to(base):
        raise PathForbidden("Artifact folder is outside of shared data")
    if not root.is_dir():
        raise ArtifactNotFound(f"Artifact {artifact_id} has no data on disk")
    return root


def resolve_inside(root: Path, rel: str = "") -> Path:

    if "\x00" in rel:
        raise InvalidPath("Invalid path")

    candidate = (root / rel.strip("/")).resolve()
    if not candidate.is_relative_to(root):
        raise PathForbidden("Path escapes artifact root")
    if not candidate.exists():
        raise ArtifactNotFound(f"Path not found: {rel}")
    return candidate
