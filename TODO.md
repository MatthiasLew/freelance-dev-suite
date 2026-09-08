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
- [ ] configure the PyPI Trusted Publisher before creating the first release tag

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
