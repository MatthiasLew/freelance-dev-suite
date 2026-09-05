# Changelog

## Unreleased

### Added

- Repository-backed `freelance work` workflow with `start`, `status`, `finish`, `resume`, and `list`
  commands, resumable context fingerprints, scope linkage, timer integration, validation state, and
  provider-reported token/cost accounting.
- Atomic work-session persistence and regression coverage for the complete work lifecycle.
- Windows jobs in the Python 3.11-3.13 CI matrix.
- Client communication module (`packages/communication`) with `MessageGenerator` creating tailored client messages across all project lifecycle stages (`intake`, `quote`, `update`, `demo`, `delivery`, `reminder`, `scope-notice`) with multi-language support (Polish and English).
- Dynamic AI model pricing management and YAML persistence in `packages/ai_cost/pricing.py`.
- CLI commands `freelance message <JOB-ID> <STAGE>` and `freelance pricing`.
- Portfolio generator module (`packages/portfolio`) creating client case studies with optional anonymization and export to `portfolio/<JOB-ID>-case-study.md`.
- Estimator calibration & heuristic learning module (`packages/estimator/calibration.py`) computing historical quote-vs-actual multipliers and variance analysis.
- GitHub Actions continuous integration pipeline (`.github/workflows/ci.yml`) validating Python 3.11, 3.12, and 3.13 with Ruff, Mypy, and Pytest coverage.
- CLI commands `freelance portfolio <JOB-ID>` and `freelance calibrate`.
- Time tracking & profitability module (`packages/tracking`) with `TimeTracker` for recording work sessions, categorized activities, and durations in `work/time-log.json`.
- `ProfitabilityCalculator` for computing effective hourly rates, profit margins, AI tooling expenses, and quote vs actual variance in `analysis/profitability-report.md`.
- CLI commands `freelance timer start`, `freelance timer stop`, `freelance timer status`, `freelance timer log`, and `freelance stats`.
- Scope-change-detector module (`packages/scope`) for detecting scope creep against baseline requirements, classifying requests (`IN_SCOPE`, `MINOR_EXTENSION`, `OUT_OF_SCOPE`, `BREAKING_CHANGE`), and calculating extra hours, AI costs, and surcharges.
- Client proposal generator creating ready-to-send change order messages in `work/scope/CHANGE-XXX-proposal.md` and detailed technical assessments in `work/scope/CHANGE-XXX-analysis.md`.
- CLI commands `freelance scope check`, `freelance scope list`, `freelance scope show`, and `freelance scope snapshot`.
- Bug-report-to-reproduction module (`packages/bugs`) for deterministic issue parsing, automatic clarifying questions generator (`questions-for-client.md`), and standalone reproduction script generator (`repro.py`).
- Bug lifecycle state management (`REPORTED`, `NEEDS_INFO`, `REPRODUCED`, `FIX_IN_PROGRESS`, `FIXED`, `REGRESSION_TESTED`, `CLOSED`) and regression test linkage.
- CLI commands `freelance bug add`, `freelance bug list`, `freelance bug show`, `freelance bug status`, `freelance bug repro`, and `freelance bug test`.
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

- Job metadata is written atomically, stale counters cannot silently reuse an existing `JOB-ID`, and
  updating archived jobs no longer creates an active duplicate.
- Handoff archives exclude dotenv secrets and symbolic links.
- Dependency counting normalizes requirement operators and duplicate constraints.
- Git scaffolding reports failed initialization, staging, or initial commit instead of a false success.
- Profitability reports prefer measured work-session AI costs over intake estimates.
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
