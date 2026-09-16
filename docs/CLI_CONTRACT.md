# Global CLI Output & Execution Contract

`freelance-dev-suite` follows a strict command-line interface contract ensuring reliability for interactive shell users, script automations, and AI agent orchestrators.

---

## 1. Standard Exit Codes

The CLI strictly maps command results to standard process exit codes:

| Exit Code | Constant | Meaning | Examples |
| :---: | :--- | :--- | :--- |
| `0` | `EXIT_SUCCESS` | Command completed successfully. | `freelance job new`, `freelance doctor` with all checks passed. |
| `1` | `EXIT_ERROR` | Runtime error, IO failure, state corruption, or internal exception. | File read failure, missing job directory, uncaught exception. |
| `2` | `EXIT_USAGE` | Invalid command syntax, missing required arguments, or unknown option. | Passed invalid flag, omitted required `--client`. |
| `3` | `EXIT_BLOCKED` | Command blocked by business rule, failed quality gate, or safety precondition. | Attempting `freelance handoff package` when tests fail, or starting work on finished job. |

---

## 2. Structured JSON Output Envelope (`--json`)

Every command supports the `--json` flag. When provided, stdout emits a single valid JSON object formatted as follows:

```json
{
  "schema_version": "1.0",
  "command": "job new",
  "status": "success",
  "exit_code": 0,
  "data": {
    "job_id": "JOB-001",
    "client": "Acme Corp",
    "status": "INTAKE"
  },
  "errors": []
}
```

### Top-Level Envelope Fields:
- `schema_version`: Version of the CLI envelope contract (currently `"1.0"`).
- `command`: Canonical name of the command invoked.
- `status`: `"success"` or `"error"`.
- `exit_code`: Numeric status code matching the process exit code.
- `data`: Object containing command-specific payload.
- `errors`: List of error messages if command failed.

### Dual Backward Compatibility:
For seamless backward compatibility with existing tests and scripts expecting direct access to payload keys (e.g., `payload["job"]`), `format_json_envelope` mirrors keys from dictionary payloads directly into the root level of the JSON response while preserving all envelope fields.

---

## 3. Safe Mutation UX: `--dry-run` and `--explain`

All commands that mutate workspace state (`job new`, `start`, `bootstrap`, `finish`, `handoff package`) support previewing actions without modifying disk:

### `--dry-run`
Simulates command execution. Evaluates preconditions, calculates outputs, and reports what actions would occur without writing to disk or acquiring locks.
```bash
freelance start JOB-001 --dry-run
```

### `--explain`
Provides a detailed step-by-step technical explanation of the operations that the command will perform (e.g., files created, locks acquired, subcommands invoked, git branches touched).
```bash
freelance job new --client "Acme" --description "Auth system" --explain
```
