"""Security and secret masking primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openrouter_key", re.compile(r"sk-or-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("connection_string", re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^\s]+")),
    ("password_assignment", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s]{8,}")),
    (
        "api_key_assignment",
        re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[^'\"\s]{12,}"),
    ),
)


@dataclass(slots=True)
class SecretFinding:
    path: str
    line: int
    kind: str
    value: str

    def masked_value(self) -> str:
        return "***" if len(self.value) <= 8 else f"{self.value[:4]}...{self.value[-4:]}"

    def masked_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "masked_value": self.masked_value(),
        }


def mask_text(text: str) -> str:
    """Mask common secret patterns in terminal/JSON output or exported files."""
    masked = text
    for kind, pattern in SECRET_PATTERNS:
        masked = pattern.sub(f"***MASKED_{kind.upper()}***", masked)
    return masked


def scan_paths_for_secrets(root: Path, paths: list[Path]) -> list[SecretFinding]:
    """Scan a list of files for secrets, skipping non-files and oversized payloads."""
    findings: list[SecretFinding] = []
    for path in paths:
        if not path.exists() or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = path.name
        if path.name == ".env":
            findings.append(SecretFinding(rel, 1, "env_file", ".env"))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    findings.append(SecretFinding(rel, line_number, kind, match.group(0)))
    return findings


def canonicalize_path(path: Path | str) -> Path:
    """Canonicalize a path, resolving symlinks, junctions, and relative segments.

    If leaf components do not exist yet, the nearest existing parent is resolved
    and non-existing segments are appended, with path normalization applied.
    """
    p = Path(path)
    try:
        return p.resolve(strict=False)
    except OSError:
        curr = p
        tail: list[str] = []
        while not curr.exists() and curr != curr.parent:
            tail.append(curr.name)
            curr = curr.parent
        try:
            base = curr.resolve(strict=False)
        except OSError:
            import os

            base = Path(os.path.normpath(os.path.abspath(curr)))
        for part in reversed(tail):
            base = base / part
        return base


def assert_safe_path(base_dir: Path, target_path: Path) -> Path:
    """Ensure target_path resolves strictly within base_dir to prevent path traversal.

    Guarantees:
    1. Full canonicalization of both base_dir and target_path (resolving symlinks/junctions).
    2. Rejection of sibling prefix tricks (e.g. /workspace/project vs /workspace/project-evil).
    3. Rejection of directory traversal components ('..').
    4. Rejection of different root/drive on Windows (e.g. C: vs D:).
    5. Case-insensitivity normalization across Windows paths.
    """
    import os

    canonical_base = canonicalize_path(base_dir)
    canonical_target = canonicalize_path(target_path)

    norm_base = os.path.normcase(os.path.normpath(str(canonical_base)))
    norm_target = os.path.normcase(os.path.normpath(str(canonical_target)))

    expected_prefix = norm_base if norm_base.endswith(os.sep) else norm_base + os.sep
    if not (norm_target == norm_base or norm_target.startswith(expected_prefix)):
        raise ValueError(
            f"Security violation: path traversal detected ({target_path} is outside {base_dir})"
        )

    try:
        rel = canonical_target.relative_to(canonical_base)
        if ".." in rel.parts:
            raise ValueError(
                f"Security violation: path traversal detected ({target_path} is outside {base_dir})"
            )
    except ValueError as exc:
        raise ValueError(
            f"Security violation: path traversal detected ({target_path} is outside {base_dir})"
        ) from exc

    return canonical_target
