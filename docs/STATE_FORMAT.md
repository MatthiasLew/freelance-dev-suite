# State Format & Schema Compatibility Specification

This document details the persistent JSON and JSONL data structures stored on disk by `freelance-dev-suite`.

---

## 1. Schema Versioning Policy

Every persistent JSON record written by `freelance-dev-suite` includes an explicit schema version field:
```json
"schema_version": "1.0"
```

### Compatibility Rules
- **Patch/Minor Upgrades (`1.x`)**: Fields may be added with backward-compatible defaults. Parsers safely read older records and fill missing fields with defaults.
- **Major Upgrades (`2.x`)**: If incompatible structure changes occur, the version increments to `2.0`. Attempting to load a file with a higher major version using an older suite will raise `IncompatibleSchemaError`.
- **Corrupted State**: Files with invalid JSON syntax, empty byte content, or malformed top-level objects raise `CorruptedStateError`.

---

## 2. File Specifications

### `job.json`
The primary metadata and state-machine record for each client job. Located at `<job_dir>/job.json`.

```json
{
  "schema_version": "1.0",
  "id": "JOB-001",
  "client": "Acme Corp",
  "description": "Integration of payments gateway",
  "source": "Upwork",
  "created_at": "2026-09-16T10:00:00+02:00",
  "status": "IN_PROGRESS",
  "budget_pln": 5000.0,
  "deadline": "2026-10-01",
  "repository": "/path/to/client/repo",
  "notes": "Client requested Stripe integration",
  "tags": ["stripe", "fastapi"]
}
```

**Job Status State Machine**:
- `INTAKE`: Newly created, repository or brief being evaluated.
- `ESTIMATED`: Quote and estimation calculations generated.
- `IN_PROGRESS`: Active implementation sessions underway.
- `REVIEW`: Work submitted for client testing or internal quality gates.
- `COMPLETED`: Verified and finalized handoff package delivered.
- `CANCELLED`: Engagement terminated early.

---

### `analysis/requirements.json`
Formal specification of functional requirements and testable acceptance criteria.

```json
{
  "schema_version": "1.0",
  "job_id": "JOB-001",
  "title": "Payment Gateway Requirements",
  "description": "Functional criteria for checkout flow",
  "requirements": [
    {
      "id": "REQ-001",
      "category": "functional",
      "title": "Webhook handling",
      "description": "Handle checkout.session.completed idempotently",
      "acceptance_criteria": [
        "Duplicate webhook delivers return 200 without double credit",
        "Signature is verified using webhook secret"
      ],
      "priority": "HIGH",
      "status": "COMPLETED"
    }
  ],
  "created_at": "2026-09-16T11:00:00+02:00",
  "updated_at": "2026-09-16T14:00:00+02:00"
}
```

---

### `work/sessions/WORK-###.json`
Structured log for each implementation session.

```json
{
  "schema_version": "1.0",
  "id": "WORK-001",
  "job_id": "JOB-001",
  "started_at": "2026-09-16T12:00:00+02:00",
  "ended_at": "2026-09-16T13:30:00+02:00",
  "duration_minutes": 90,
  "status": "VERIFIED",
  "notes": "Implemented webhook verification",
  "git_commit_before": "a1b2c3d",
  "git_commit_after": "e4f5g6h",
  "diff_stat": "4 files changed, 120 insertions(+), 12 deletions(-)"
}
```

---

### `scope/changes.json`
Audit log of out-of-scope client requests and calculated price adjustments.

```json
{
  "schema_version": "1.0",
  "job_id": "JOB-001",
  "changes": [
    {
      "id": "CHG-001",
      "date": "2026-09-16T14:30:00+02:00",
      "description": "Support PayPal in addition to Stripe",
      "source_text": "Could we also add PayPal button on the checkout page?",
      "is_scope_creep": true,
      "estimated_hours": 8.0,
      "surcharge_pln": 1200.0,
      "status": "PROPOSED"
    }
  ]
}
```

---

### `history/events.jsonl`
Append-only chronological audit log of all business events.

Each line is a self-contained JSON object:
```json
{"event_id": "ev-8f716e8b", "timestamp": "2026-09-16T10:00:00+02:00", "event_type": "job_created", "job_id": "JOB-001", "details": {"client": "Acme Corp", "source": "Upwork"}}
{"event_id": "ev-9a8b7c6d", "timestamp": "2026-09-16T10:30:00+02:00", "event_type": "intake_analyzed", "job_id": "JOB-001", "details": {"risk_level": "LOW", "files_scanned": 42}}
{"event_id": "ev-0b1c2d3e", "timestamp": "2026-09-16T11:00:00+02:00", "event_type": "estimate_created", "job_id": "JOB-001", "details": {"price_pln": 5000.0, "hours": 32.0}}
```
