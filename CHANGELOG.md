# Changelog

## Unreleased

### Added

- Client-handoff module (`packages/handoff`) providing automated Final Quality Gate checks (requirements completion, clean git working tree, code hygiene / debug code scan, secrets & API credentials detection, documentation validation, and technical tests runner).
- Client handoff package generator creating `handoff/` deliverables (`README_CLIENT.md`, `INSTALLATION.md`, `USER_GUIDE.md`, `CHANGELOG.md`, `TEST_REPORT.md`, `REQUIREMENTS.md`, and clean `release.zip` archive).
- CLI commands `freelance handoff <JOB-ID>` and `freelance finish <JOB-ID>` with support for `--force`, `--archive`, `--skip-technical`, and `--json`.
- Client-project-bootstrap module (`packages/bootstrap`) with 8 starter templates across Python (`python-cli`, `python-api`, `python-desktop`, `data-processing`, `automation-script`) and C# (`csharp-console`, `csharp-desktop`, `csharp-library`).
- Automatic project scaffolding with test frameworks, linter/typecheck configs, docs (`REQUIREMENTS.md`, `ACCEPTANCE.md`, `HANDOFF.md`), git initialization, and `ai-dev-cli-tools` integration.
- CLI commands `freelance templates`, `freelance bootstrap <TEMPLATE>`, and `freelance start <JOB-ID>`.
- Requirements-to-checklist module (`packages/requirements`) with `RequirementsSpec`, `RequirementItem`, and `AcceptanceCriterion` data models.
- Deterministic requirement extraction, section classification, and bidirectional Markdown synchronization (`client/requirements.md` <-> `work/checklist.md` <-> `analysis/requirements.json`).
- CLI command `freelance requirements` supporting text generation, file input, `--confirm`, `--changed`, `--check`, `--uncheck`, `--checklist`, and `--json`.
- Project intake backed by `ai-dev scan`, `map`, `check`, and `context build`.
- Structured AI-cost estimates with explicit assumptions and configurable pricing.
- Full quote calculation and JSON output for `analyze` and `estimate`.
- Integration tests for the MVP workflow and current `ai-dev` JSON contracts.

### Fixed

- Intake no longer silently reports missing capabilities when `ai-dev` is unavailable.
- Repository maps use the current `file_count_scanned` field.
- PEP 621 dependencies are counted.
- Minimum technical prices are always rounded upward.
- `jobs --all` includes jobs stored under `finished`.

## 0.1.0 — 2026-09-01

### Added

- Project foundation: `pyproject.toml`, repo structure, CI-ready layout.
- **freelance-workspace**: `Job` model with JSON persistence, `JOB-ID` generation, status tracking.
- **Common CLI**: `freelance job new`, `freelance jobs`, `freelance status <JOB-ID>`.
- User configuration via `~/.freelance/config.yaml`.
- Unit tests for workspace, storage, and CLI.
