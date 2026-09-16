"""Tests for persistent state schema versioning, backward compatibility, and corruption handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from freelance_cli.models.job import Job
from packages.storage_utils import (
    CURRENT_STATE_SCHEMA_VERSION,
    CorruptedStateError,
    IncompatibleSchemaError,
    atomic_write_json,
    atomic_write_state,
    safe_read_json,
)


def test_safe_read_json_legacy_file_without_schema_version(tmp_path: Path) -> None:
    """Legacy JSON files created without schema_version should default to 1.0."""
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(json.dumps({"name": "legacy_project", "count": 42}), encoding="utf-8")

    data = safe_read_json(legacy_file)
    assert data["name"] == "legacy_project"
    assert data["count"] == 42
    assert data.get("schema_version") == CURRENT_STATE_SCHEMA_VERSION


def test_safe_read_json_valid_schema_version(tmp_path: Path) -> None:
    """JSON files with current schema version should load without errors."""
    valid_file = tmp_path / "valid.json"
    atomic_write_state(valid_file, {"status": "ok", "value": 100})

    data = safe_read_json(valid_file)
    assert data["status"] == "ok"
    assert data["value"] == 100
    assert data["schema_version"] == CURRENT_STATE_SCHEMA_VERSION


def test_atomic_write_json_generic_does_not_mutate_technical_data(tmp_path: Path) -> None:
    """Technical/non-state JSON must remain structurally unchanged without schema mutation."""

    tech_file = tmp_path / "technical_report.json"
    original_data = {
        "report_type": "benchmark",
        "durations": [1.2, 3.4, 0.5],
        "metadata": {"runner": "pytest"},
    }
    atomic_write_json(tech_file, original_data)

    raw_loaded = json.loads(tech_file.read_text(encoding="utf-8"))
    assert "schema_version" not in raw_loaded
    assert raw_loaded == original_data


def test_safe_read_json_future_incompatible_version(tmp_path: Path) -> None:
    """Files from a future major schema version should be rejected with IncompatibleSchemaError."""
    future_file = tmp_path / "future.json"
    future_file.write_text(
        json.dumps({"schema_version": "2.0", "data": "future_feature"}), encoding="utf-8"
    )

    with pytest.raises(IncompatibleSchemaError) as exc_info:
        safe_read_json(future_file, expected_version="1.0")
    assert "Unsupported schema_version '2.0'" in str(exc_info.value)


def test_safe_read_json_corrupted_file(tmp_path: Path) -> None:
    """Non-JSON or broken JSON files should raise CorruptedStateError."""
    corrupted_file = tmp_path / "broken.json"
    corrupted_file.write_text("{ incomplete json: ", encoding="utf-8")

    with pytest.raises(CorruptedStateError) as exc_info:
        safe_read_json(corrupted_file)
    assert "Failed to read state file" in str(exc_info.value)


def test_safe_read_json_non_dict(tmp_path: Path) -> None:
    """Files that decode to lists or primitives should raise CorruptedStateError."""
    list_file = tmp_path / "list.json"
    list_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(CorruptedStateError) as exc_info:
        safe_read_json(list_file)
    assert "Expected JSON object" in str(exc_info.value)


def test_safe_read_json_empty_file(tmp_path: Path) -> None:
    """Empty (0-byte or whitespace-only) state files should raise CorruptedStateError."""
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(CorruptedStateError) as exc_info:
        safe_read_json(empty_file)
    assert "State file is empty" in str(exc_info.value)


def test_safe_read_json_tolerates_unknown_additive_fields(tmp_path: Path) -> None:
    """Additive fields from future tools or plugins are tolerated on JSON read."""
    state_file = tmp_path / "extended_state.json"
    extended_data = {
        "job_id": "JOB-001",
        "custom_plugin_tag": "ai-dev-integration",
        "nested_metadata": {"flag": True, "scores": [1, 2, 3]},
    }
    atomic_write_state(state_file, extended_data)

    loaded = safe_read_json(state_file)
    assert loaded["custom_plugin_tag"] == "ai-dev-integration"
    assert loaded["nested_metadata"]["scores"] == [1, 2, 3]
    assert loaded["schema_version"] == CURRENT_STATE_SCHEMA_VERSION


def test_model_round_trip_unknown_fields_tolerated_not_preserved(tmp_path: Path) -> None:
    """Documented contract: unknown fields are tolerated on read, not preserved on round-trip."""
    state_file = tmp_path / "job.json"

    input_data = {
        "schema_version": "1.0",
        "id": "JOB-001",
        "client": "Acme Corp",
        "description": "Round-trip preservation test",
        "future_field": {"nested": True, "flag": "custom"},
    }
    atomic_write_json(state_file, input_data)

    # 1. safe_read_json tolerates the unknown field
    loaded_dict = safe_read_json(state_file)
    assert loaded_dict["future_field"]["nested"] is True

    # 2. Deserializing into model ignores unknown field without crashing
    job = Job.from_dict(loaded_dict)
    assert job.id == "JOB-001"
    assert job.client == "Acme Corp"

    # 3. Serializing and saving back
    atomic_write_json(state_file, job.to_dict())

    # 4. Result: future_field is omitted by dataclass model serialization
    saved_raw = json.loads(state_file.read_text(encoding="utf-8"))
    assert "future_field" not in saved_raw
    assert saved_raw["id"] == "JOB-001"
    assert saved_raw["schema_version"] == "1.0"


def test_safe_read_json_malformed_version_rejected(tmp_path: Path) -> None:
    """Non-numeric or malformed schema versions should be rejected cleanly."""
    malformed_file = tmp_path / "malformed_ver.json"
    malformed_file.write_text(
        json.dumps({"schema_version": "invalid_version", "key": "val"}), encoding="utf-8"
    )

    with pytest.raises(IncompatibleSchemaError) as exc_info:
        safe_read_json(malformed_file)
    assert "Malformed schema_version" in str(exc_info.value)
