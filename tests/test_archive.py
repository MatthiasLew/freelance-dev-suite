"""Tests for job export, verified archive format, and safe import with path traversal protection."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.models.job import Job
from packages.archive.manager import ArchiveManager
from packages.storage_utils import CorruptedStateError, atomic_write_json


def test_export_and_import_roundtrip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    job_dir = workspace / "active" / "JOB-001-test"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "analysis").mkdir(parents=True, exist_ok=True)

    job = Job(id="JOB-001", client="Acme Corp", description="Secure portal", budget_pln=5000.0)
    atomic_write_json(job_dir / "job.json", job.to_dict())
    atomic_write_json(job_dir / "analysis" / "notes.json", {"meeting": "kickoff"})

    archiver = ArchiveManager()
    archive_path = archiver.export_job(job, job_dir)
    assert archive_path.exists()
    assert archive_path.name == "JOB-001-export.tar.gz"

    # Verify manifest
    manifest = archiver.read_manifest(archive_path)
    assert manifest["job_id"] == "JOB-001"
    assert manifest["client"] == "Acme Corp"
    assert "checksums" in manifest
    assert "job.json" in manifest["checksums"]

    # Import into new workspace
    new_workspace = tmp_path / "imported_workspace"
    new_workspace.mkdir()
    imported_job = archiver.import_job(archive_path, new_workspace)

    assert imported_job.id == "JOB-001"
    assert imported_job.client == "Acme Corp"
    imported_dirs = list((new_workspace / "active").glob("JOB-001*"))
    assert len(imported_dirs) == 1
    assert (imported_dirs[0] / "job.json").exists()


def test_import_checksum_mismatch_raises_corrupted_state_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    job_dir = workspace / "active" / "JOB-002-test"
    job_dir.mkdir(parents=True, exist_ok=True)

    job = Job(id="JOB-002", client="Beta Corp", description="Test job")
    atomic_write_json(job_dir / "job.json", job.to_dict())

    archiver = ArchiveManager()
    archive_path = archiver.export_job(job, job_dir)

    # Read archive, tamper with manifest checksum
    tampered_tar = tmp_path / "tampered.tar.gz"
    with (
        tarfile.open(archive_path, "r:gz") as src_tar,
        tarfile.open(tampered_tar, "w:gz") as dst_tar,
    ):
        for member in src_tar.getmembers():
            f = src_tar.extractfile(member)
            if member.name == "manifest.json" and f is not None:
                manifest_data = json.loads(f.read().decode("utf-8"))
                manifest_data["checksums"]["job.json"] = "bad_checksum_hash_1234567890"
                new_bytes = json.dumps(manifest_data).encode("utf-8")
                tarinfo = tarfile.TarInfo(name="manifest.json")
                tarinfo.size = len(new_bytes)
                dst_tar.addfile(tarinfo, io.BytesIO(new_bytes))
            elif f is not None:
                dst_tar.addfile(member, f)

    target_ws = tmp_path / "target_ws"
    target_ws.mkdir()
    with pytest.raises(CorruptedStateError) as exc_info:
        archiver.import_job(tampered_tar, target_ws)
    assert "Checksum mismatch" in str(exc_info.value)


def test_import_path_traversal_attack_rejected(tmp_path: Path) -> None:
    """An archive with malicious '../' relative path members must be blocked."""
    malicious_tar = tmp_path / "malicious.tar.gz"
    with tarfile.open(malicious_tar, "w:gz") as tar:
        # Add a file trying to break out to parent directories
        payload = b"MALICIOUS_OVERWRITE"
        ti = tarfile.TarInfo(name="../../etc/passwd")
        ti.size = len(payload)
        tar.addfile(ti, io.BytesIO(payload))

        manifest = {"manifest_version": "1.0", "job_id": "EVIL", "checksums": {}}
        m_bytes = json.dumps(manifest).encode("utf-8")
        m_ti = tarfile.TarInfo(name="manifest.json")
        m_ti.size = len(m_bytes)
        tar.addfile(m_ti, io.BytesIO(m_bytes))

    archiver = ArchiveManager()
    with pytest.raises((ValueError, CorruptedStateError)) as exc_info:
        archiver.read_manifest(malicious_tar)
    assert (
        "path traversal" in str(exc_info.value).lower()
        or "security violation" in str(exc_info.value).lower()
    )


def test_import_symlink_entry_rejected(tmp_path: Path) -> None:
    """An archive containing symlink entries must be blocked."""
    evil_tar = tmp_path / "symlink.tar.gz"
    with tarfile.open(evil_tar, "w:gz") as tar:
        ti = tarfile.TarInfo(name="data/evil_link")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/shadow"
        tar.addfile(ti)

        manifest = {"job_id": "JOB-001", "checksums": {}}
        m_bytes = json.dumps(manifest).encode("utf-8")
        m_ti = tarfile.TarInfo(name="manifest.json")
        m_ti.size = len(m_bytes)
        tar.addfile(m_ti, io.BytesIO(m_bytes))

    archiver = ArchiveManager()
    with pytest.raises(ValueError) as exc_info:
        archiver.validate_archive(evil_tar)
    assert "link entries not allowed" in str(exc_info.value).lower()


def test_import_unmanifested_file_rejected(tmp_path: Path) -> None:
    """An archive containing extra data files not declared in manifest checksums must be blocked."""
    unmanifested_tar = tmp_path / "unmanifested.tar.gz"
    with tarfile.open(unmanifested_tar, "w:gz") as tar:
        payload = b"unmanifested backdoor payload"
        ti = tarfile.TarInfo(name="data/backdoor.py")
        ti.size = len(payload)
        tar.addfile(ti, io.BytesIO(payload))

        manifest = {"job_id": "JOB-001", "checksums": {}}
        m_bytes = json.dumps(manifest).encode("utf-8")
        m_ti = tarfile.TarInfo(name="manifest.json")
        m_ti.size = len(m_bytes)
        tar.addfile(m_ti, io.BytesIO(m_bytes))

    archiver = ArchiveManager()
    with pytest.raises(ValueError) as exc_info:
        archiver.validate_archive(unmanifested_tar)
    assert "unmanifested file" in str(exc_info.value).lower()


def test_import_duplicate_member_rejected(tmp_path: Path) -> None:
    """An archive with duplicate member names must be rejected."""
    dup_tar = tmp_path / "duplicate.tar.gz"
    with tarfile.open(dup_tar, "w:gz") as tar:
        payload = b"content"
        t1 = tarfile.TarInfo(name="data/file.txt")
        t1.size = len(payload)
        tar.addfile(t1, io.BytesIO(payload))

        t2 = tarfile.TarInfo(name="data/file.txt")
        t2.size = len(payload)
        tar.addfile(t2, io.BytesIO(payload))

        manifest = {"job_id": "JOB-001", "checksums": {}}
        m_bytes = json.dumps(manifest).encode("utf-8")
        m_ti = tarfile.TarInfo(name="manifest.json")
        m_ti.size = len(m_bytes)
        tar.addfile(m_ti, io.BytesIO(m_bytes))

    archiver = ArchiveManager()
    with pytest.raises(CorruptedStateError) as exc_info:
        archiver.validate_archive(dup_tar)
    assert "duplicate entry" in str(exc_info.value).lower()


def test_cli_archive_human_readable_and_missing(cli_runner: CliRunner, tmp_path: Path) -> None:
    """CLI export and import must provide human-readable output and reject missing jobs/files."""
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "ArchiveHuman",
            "--description",
            "Archive test",
            "--source",
            "Direct",
        ],
    )
    res = cli_runner.invoke(main, ["export", "JOB-001"])
    assert res.exit_code == 0
    assert "Job JOB-001 exported successfully" in res.output

    # Export missing job ID
    res_miss = cli_runner.invoke(main, ["export", "JOB-999"])
    assert res_miss.exit_code != 0
    assert "not found" in res_miss.output.lower()

    # Import missing archive file
    res_imp_miss = cli_runner.invoke(main, ["import", str(tmp_path / "nonexistent.tar.gz")])
    assert res_imp_miss.exit_code != 0


def test_export_and_import_cli(cli_runner: CliRunner, tmp_path: Path) -> None:
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "ExportClient",
            "--description",
            "Export test",
            "--source",
            "Direct",
        ],
    )
    res_exp = cli_runner.invoke(main, ["export", "JOB-001", "--json"])
    assert res_exp.exit_code == 0
    payload = json.loads(res_exp.output)
    archive_path = payload["archive_path"]
    assert Path(archive_path).exists()

    res_imp = cli_runner.invoke(main, ["import", archive_path, "--force", "--json"])
    assert res_imp.exit_code == 0
    imp_payload = json.loads(res_imp.output)
    assert imp_payload["job"]["id"] == "JOB-001"
