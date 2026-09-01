# Changelog

## 0.1.0 — 2026-09-01

### Added

- Project foundation: `pyproject.toml`, repo structure, CI-ready layout.
- **freelance-workspace**: `Job` model with JSON persistence, `JOB-ID` generation, status tracking.
- **Common CLI**: `freelance job new`, `freelance jobs`, `freelance status <JOB-ID>`.
- User configuration via `~/.freelance/config.yaml`.
- Unit tests for workspace, storage, and CLI.
