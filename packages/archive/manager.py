"""Safe export and import of portable freelance job archives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from freelance_cli.models.job import Job
from packages.security.secrets import assert_safe_path
from packages.storage_utils import (
    CURRENT_STATE_SCHEMA_VERSION,
    CorruptedStateError,
)
from packages.workspace.storage import _slugify, find_job_by_id, find_job_dir, load_job

EXPORT_VERSION = "1.0"
MAX_ARCHIVE_MEMBERS = 5_000
MAX_MEMBER_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_TOTAL_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB
IGNORED_ARCHIVE_NAMES = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".coverage",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(131072):
            h.update(chunk)
    return h.hexdigest()


class ArchiveManager:
    """Manages secure packaging, integrity verification, and safe restoration of jobs."""

    def export_job(
        self,
        job: Job,
        job_dir: Path,
        output_archive: Path | None = None,
    ) -> Path:
        """Export job workspace into a portable tar.gz bundle with checksum manifest."""
        if output_archive is None:
            dest = job_dir.parent / f"{job.id}-export.tar.gz"
        else:
            dest = output_archive
        dest.parent.mkdir(parents=True, exist_ok=True)

        dest_canonical = dest.resolve()
        dotenv_templates = {".env.example", ".env.sample", ".env.template"}

        files_to_pack: list[tuple[Path, str]] = []
        checksums: dict[str, str] = {}

        for root_dir, dirnames, filenames in os.walk(job_dir):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_ARCHIVE_NAMES]

            for fname in filenames:
                file_path = Path(root_dir) / fname
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                if fname.startswith(".env") and fname not in dotenv_templates:
                    continue
                if file_path.resolve() == dest_canonical:
                    continue

                rel = file_path.relative_to(job_dir)
                rel_str = str(rel).replace("\\", "/")
                files_to_pack.append((file_path, rel_str))
                checksums[rel_str] = _sha256_file(file_path)

        manifest: dict[str, Any] = {
            "export_version": EXPORT_VERSION,
            "schema_version": CURRENT_STATE_SCHEMA_VERSION,
            "job_id": job.id,
            "client": job.client,
            "exported_at": datetime.now().astimezone().isoformat(),
            "files_count": len(files_to_pack),
            "checksums": checksums,
        }

        # Write archive
        with tarfile.open(dest, "w:gz") as tar:
            # Write manifest first
            manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
                "utf-8"
            )
            import io

            tar_info = tarfile.TarInfo(name="manifest.json")
            tar_info.size = len(manifest_bytes)
            tar_info.mtime = int(datetime.now().timestamp())
            tar.addfile(tar_info, io.BytesIO(manifest_bytes))

            for file_path, arcname in files_to_pack:
                tar.add(file_path, arcname=f"data/{arcname}")

        return dest

    def validate_archive(self, archive_path: Path) -> dict[str, Any]:
        """Validate archive format, manifest, and verify there are no path traversal attempts."""
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ValueError(
                        f"Security violation: archive contains {len(members)} entries, "
                        f"exceeding maximum limit of {MAX_ARCHIVE_MEMBERS}"
                    )

                total_uncompressed = sum(m.size for m in members)
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"Security violation: archive total uncompressed size "
                        f"{total_uncompressed} bytes exceeds limit of "
                        f"{MAX_TOTAL_UNCOMPRESSED_BYTES} bytes"
                    )

                manifest_member = None
                seen_names: set[str] = set()
                data_members: list[str] = []

                for member in members:
                    name = member.name
                    if name in seen_names:
                        raise CorruptedStateError(f"Duplicate entry in archive: '{name}'")
                    seen_names.add(name)

                    # Deny symlinks, hardlinks, FIFOs, char/block devices
                    if member.issym() or member.islnk():
                        raise ValueError(
                            f"Security violation: link entries not allowed in archive: '{name}'"
                        )
                    if not (member.isreg() or member.isdir()):
                        raise ValueError(
                            f"Security violation: non-regular file entry in archive: '{name}'"
                        )

                    if member.size > MAX_MEMBER_SIZE_BYTES:
                        raise ValueError(
                            f"Security violation: file '{name}' size {member.size} bytes "
                            f"exceeds maximum allowed size of {MAX_MEMBER_SIZE_BYTES} bytes"
                        )

                    # Traversal validation
                    if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                        raise ValueError(
                            f"Security violation: path traversal detected in member name '{name}'"
                        )
                    if re.match(r"^[a-zA-Z]:", name):
                        raise ValueError(
                            f"Security violation: absolute drive path in member name '{name}'"
                        )

                    if name == "manifest.json":
                        manifest_member = member
                    elif name.startswith("data/") and member.isreg():
                        data_members.append(name[len("data/") :])

                if manifest_member is None:
                    raise CorruptedStateError("manifest.json is missing in archive")

                f = tar.extractfile(manifest_member)
                if f is None:
                    raise CorruptedStateError("manifest.json is empty in archive")
                parsed = json.loads(f.read().decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise CorruptedStateError("manifest.json must contain a JSON object")
                manifest: dict[str, Any] = cast(dict[str, Any], parsed)

                job_id = manifest.get("job_id")
                if not job_id or not isinstance(job_id, str):
                    raise CorruptedStateError("Archive manifest does not specify a valid job_id")

                checksums = manifest.get("checksums")
                if not isinstance(checksums, dict):
                    raise CorruptedStateError("Archive manifest does not specify checksums dict")

                # Verify every data file in the archive is in manifest checksums
                for rel_name in data_members:
                    if rel_name not in checksums:
                        raise ValueError(
                            f"Security violation: archive contains unmanifested file '{rel_name}'"
                        )

                return manifest
        except (tarfile.TarError, json.JSONDecodeError, KeyError) as exc:
            raise CorruptedStateError(
                f"Invalid or corrupted archive {archive_path}: {exc}"
            ) from exc

    read_manifest = validate_archive

    def import_job(
        self,
        archive_path: Path,
        workspace_root: Path,
        force: bool = False,
    ) -> Job:
        """Safely extract and register a job from an archive into workspace_root."""
        manifest = self.validate_archive(archive_path)
        job_id = str(manifest["job_id"])

        existing_job = find_job_by_id(job_id, workspace_root)
        if existing_job and not force:
            raise ValueError(f"Job {job_id} already exists in workspace. Use --force to overwrite.")

        checksums: dict[str, str] = manifest["checksums"]

        # Stage in temporary directory first (fail-safe atomic extraction)
        tmp_staging_dir = workspace_root / ".tmp" / f"import-{job_id}-{uuid.uuid4().hex}"
        tmp_staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name == "manifest.json" or not member.name.startswith("data/"):
                        continue
                    if not member.isreg():
                        continue

                    rel_name = member.name[len("data/") :]
                    dest_file = tmp_staging_dir / rel_name
                    assert_safe_path(tmp_staging_dir, dest_file)

                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    extracted_f = tar.extractfile(member)
                    if extracted_f is None:
                        raise CorruptedStateError(f"Failed to extract member '{member.name}'")

                    hasher = hashlib.sha256()
                    with open(dest_file, "wb") as out_f:
                        while chunk := extracted_f.read(131072):
                            hasher.update(chunk)
                            out_f.write(chunk)

                    actual_sha = hasher.hexdigest()
                    if actual_sha != checksums.get(rel_name):
                        raise CorruptedStateError(
                            f"Checksum mismatch for {rel_name}: "
                            f"expected {checksums.get(rel_name)}, got {actual_sha}"
                        )

            # Validate imported job.json exists and is valid
            job_json = tmp_staging_dir / "job.json"
            if not job_json.exists():
                raise CorruptedStateError(f"Imported archive for {job_id} is missing job.json")

            job = load_job(job_json)

            # Target directory under active/
            active_dir = workspace_root / "active"
            active_dir.mkdir(parents=True, exist_ok=True)

            existing_dir = find_job_dir(job_id, workspace_root)
            if existing_dir is not None and existing_dir.exists():
                target_dir = existing_dir
                shutil.rmtree(target_dir, ignore_errors=True)
            else:
                target_dir = active_dir / f"{job_id}-{_slugify(job.client + '-' + job.description)}"

            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)

            try:
                os.replace(tmp_staging_dir, target_dir)
            except OSError:
                shutil.move(str(tmp_staging_dir), str(target_dir))

            return job
        finally:
            if tmp_staging_dir.exists():
                shutil.rmtree(tmp_staging_dir, ignore_errors=True)
