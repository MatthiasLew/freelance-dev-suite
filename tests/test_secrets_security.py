"""Tests for security utilities: secret masking, file scanning, and path traversal guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.security.secrets import (
    assert_safe_path,
    mask_text,
    scan_paths_for_secrets,
)


def test_mask_text_openai_key() -> None:
    synthetic_key = "sk-testdummy" + "0" * 24
    text = f"Here is my key: {synthetic_key} for API calls"
    masked = mask_text(text)
    assert synthetic_key not in masked
    assert "***MASKED_OPENAI_KEY***" in masked


def test_mask_text_anthropic_key() -> None:
    text = "Anthropic key is sk-ant-api03-abcdef1234567890abcdef1234567890-xyz"
    masked = mask_text(text)
    assert "sk-ant-api03" not in masked
    assert "***MASKED_ANTHROPIC_KEY***" in masked


def test_mask_text_github_token() -> None:
    text = "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
    masked = mask_text(text)
    assert "ghp_1234567890" not in masked
    assert "***MASKED_GITHUB_TOKEN***" in masked


def test_mask_text_password_in_uri() -> None:
    text = "postgres://user:superSecretPassword123@localhost:5432/mydb"
    masked = mask_text(text)
    assert "superSecretPassword123" not in masked
    assert "***MASKED_CONNECTION_STRING***" in masked


def test_assert_safe_path_valid(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    child = base / "subdir" / "file.txt"
    safe = assert_safe_path(base, child)
    assert safe == child.resolve()


def test_assert_safe_path_traversal_attack(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    malicious = base / ".." / "outside.txt"
    with pytest.raises(ValueError) as exc_info:
        assert_safe_path(base, malicious)
    assert "path traversal detected" in str(exc_info.value).lower()


def test_assert_safe_path_sibling_prefix_attack(tmp_path: Path) -> None:
    """Sibling prefix trick (/workspace/project vs /workspace/project-evil) must be rejected."""
    base = tmp_path / "project"
    base.mkdir()
    sibling_evil = tmp_path / "project-evil"
    sibling_evil.mkdir()
    sibling_file = sibling_evil / "pwn.txt"

    with pytest.raises(ValueError) as exc_info:
        assert_safe_path(base, sibling_evil)
    assert "path traversal detected" in str(exc_info.value).lower()

    with pytest.raises(ValueError) as exc_info2:
        assert_safe_path(base, sibling_file)
    assert "path traversal detected" in str(exc_info2.value).lower()


def test_assert_safe_path_absolute_external_and_dots(tmp_path: Path) -> None:
    """Absolute external path and complex dot traversal must be rejected."""
    base = tmp_path / "workspace"
    base.mkdir()
    external = tmp_path / "other" / "secret.env"

    with pytest.raises(ValueError) as exc_info:
        assert_safe_path(base, external)
    assert "path traversal detected" in str(exc_info.value).lower()

    nested_dots = base / "a" / "b" / ".." / ".." / ".." / "escape.txt"
    with pytest.raises(ValueError) as exc_info2:
        assert_safe_path(base, nested_dots)
    assert "path traversal detected" in str(exc_info2.value).lower()


def test_assert_safe_path_spaces_and_unicode(tmp_path: Path) -> None:
    """Paths containing whitespace and Unicode characters must resolve safely."""
    base = tmp_path / "katalog zlecenia"
    base.mkdir()
    child_unicode = base / "zażółć gęślą jaźń" / "dane projektu 2026.json"
    safe = assert_safe_path(base, child_unicode)
    assert safe.name == "dane projektu 2026.json"
    assert "zażółć gęślą jaźń" in str(safe)


def test_assert_safe_path_symlink_escape(tmp_path: Path) -> None:
    """Symlinks inside base_dir pointing outside base_dir must be rejected."""
    base = tmp_path / "base"
    base.mkdir()
    secret_dir = tmp_path / "secret_external"
    secret_dir.mkdir()
    secret_file = secret_dir / "passwords.txt"
    secret_file.write_text("secret_data", encoding="utf-8")

    link = base / "external_link"
    try:
        link.symlink_to(secret_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/privilege level")

    with pytest.raises(ValueError) as exc_info:
        assert_safe_path(base, link)
    assert "path traversal detected" in str(exc_info.value).lower()


def test_scan_paths_for_secrets(tmp_path: Path) -> None:
    synthetic_token = "sk-proj-testdummy" + "0" * 20
    doc = tmp_path / "notes.txt"
    doc.write_text(f"My openAI token: {synthetic_token}\nClean line", encoding="utf-8")

    findings = scan_paths_for_secrets(tmp_path, [doc])
    assert len(findings) >= 1
    assert any(f.kind == "openai_key" for f in findings)
    assert findings[0].masked_value() != synthetic_token
