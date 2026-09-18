# TODO

## P0 — MVP (before first freelance job)

- [x] freelance-workspace
- [x] common CLI (`freelance job new`, `freelance jobs`, `freelance status`)
- [x] project-intake-analyzer
- [x] ai-cost-estimator
- [x] freelance-estimator

### MVP hardening follow-ups

- [x] replace bundled pricing snapshot with user-maintained/current provider data before quoting
- [x] calibrate estimation heuristics against completed freelance jobs
- [x] add wheel installation smoke test and CI workflow
- [x] add interprocess persistence locks and durable atomic writes
- [x] add full installed lifecycle coverage with `ai-dev-cli-tools`
- [x] add repository-history secret scanning
- [x] add tag-based Trusted Publishing and GitHub releases
- [x] split the CLI entrypoint into command-family modules
- [x] configure the PyPI Trusted Publisher (completed for v0.1.0 and v0.1.1 releases)


## P1 — First clients

- [x] requirements-to-checklist
- [x] client-project-bootstrap
- [x] client-handoff

## P2 — After first real jobs

- [x] bug-report-to-reproduction
- [x] scope-change-detector

## P3 — Optimization

- [x] time tracker
- [x] profitability tracker
- [x] estimator learning
- [x] portfolio generator
- [x] client communication helper

## P4 — Repository-backed delivery workflow

- [x] resumable `freelance work` sessions
- [x] scope and requirement linkage for development tasks
- [x] incremental `ai-dev task` preparation and changed-file validation
- [x] provider-reported token and AI-cost accounting
- [x] measured work-session costs in profitability reports
- [x] Linux and Windows CI matrix

## P5 — Engineering Maturity & Production Standards

- [x] persistent schema versioning (`1.0`) and schema compatibility guardrails
- [x] re-entrant cross-process file locking with thread-local re-entrancy tracking
- [x] provider-agnostic secret redaction and path traversal guards
- [x] global CLI exit code contract (`0`, `1`, `2`, `3`) and structured JSON envelope
- [x] system diagnostics CLI (`freelance doctor`) and config inspector (`freelance config`)
- [x] append-only business event audit timeline (`freelance history`)
- [x] portable workspace archive export/import with SHA-256 verification and Zip Slip protection
- [x] local STDIO Model Context Protocol (MCP) server for Cursor / Claude Desktop
- [x] safe mutation UX with `--dry-run` and `--explain`
- [x] complete engineering documentation suite in `docs/`
- [x] automated GitHub Actions CodeQL security scanning
- [x] branch test coverage boosted to 83.42% (fail_under raised to 82%)

## Release v0.2.0 Readiness & Polish

- [x] align timer concurrency tests with single-active-session-per-job model and add multi-job coverage
- [x] configure Gitleaks allowlist and safe test fixtures for secret masking validation
- [x] remove local paths and update documentation links in README
- [x] add CI, CodeQL, PyPI, Python, and License status badges to README
- [x] prepare package metadata, CHANGELOG, and test suite for v0.2.0 release

## P6 — Performance Optimization & Benchmark Audit (v0.2.1)

- [x] baseline performance audit and reproducible benchmark harness (`benchmarks/run_benchmarks.py`)
- [x] $O(1)$ fast-path backwards seek (8KB tail buffer) with $O(N)$ sequence-recovery fallback for append-only timeline
- [x] deferred `FileLock` loading and lazy CLI command imports (reducing cold startup latency by ~1.8x)
- [x] single-pass streaming archive import with in-flight SHA-256 calculation
- [x] low-overhead workspace directory scanning with `os.scandir` and high-watermark job ID caching
- [x] work session, bug report, and scope change processing optimizations
- [x] cProfile hotspot analysis (`benchmarks/profile_hotspots.py`) confirming physical I/O and `fsync` dominance
- [x] evaluate native acceleration: Rust/C extension not justified at this stage (revisit native acceleration only if future profiling identifies meaningful CPU-bound hotspots)
- [x] expand regression test suite to 241 passed tests (83.11% branch coverage)
- [x] prepare package metadata, documentation, and release artifacts for v0.2.1
