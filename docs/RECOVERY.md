# Disaster Recovery & State Troubleshooting

This guide explains how to detect, diagnose, and recover from exceptional states, corrupted records, stale locks, or system failures.

---

## 1. Automated Health Diagnostics (`freelance doctor`)

The first step in any troubleshooting process is running the doctor command:

```bash
freelance doctor
# or for machine-parseable diagnostics
freelance doctor --json
```

`freelance doctor` scans and reports on:
1. **Python Runtime**: Verifies Python `>= 3.11`.
2. **Workspace Permissions**: Ensures read/write accessibility to `~/.freelance` and active job folders.
3. **Git Tooling**: Verifies git executable presence and operational health.
4. **ai-dev Technical Engine**: Verifies `ai-dev` installation and version (`>= 1.2.0`).
5. **Persistent State Integrity**: Reads every `job.json` in `active/`, checking schema version and JSON validity.

If any job record is unparseable or outdated, `freelance doctor` highlights the specific file path.

---

## 2. Resolving Stale Locks

If a process was terminated ungracefully (`kill -9`, power outage, or OS crash) while holding a lock, a `.lock` file may remain:

- `<job_dir>/.job.lock`
- `<job_dir>/.work.lock`
- `~/.freelance/.timeline.lock`

### Resolution Procedure:
1. Ensure no `freelance` or `ai-dev` processes are currently running:
   - Linux/macOS: `ps aux | grep freelance`
   - Windows: `Get-Process | Where-Object { $_.ProcessName -like "*freelance*" }`
2. `storage_lock` uses `filelock`, which normally releases locks automatically when the holding OS process terminates.
3. If an abandoned lock file remains and prevents access, manually remove the `.lock` file:
   ```bash
   rm ~/.freelance/active/JOB-001/.job.lock
   ```

---

## 3. Handling Corrupted State Files

If a power cut or disk glitch corrupts a state file (triggering `CorruptedStateError`):
1. Locate the affected file (`<job_dir>/job.json`, `requirements.json`, etc.).
2. Inspect if a sibling `.tmp` file exists (`<filename>.<pid>.<uuid>.tmp`). If so, the temporary file may contain the intact pre-crash or post-crash contents.
3. Restore from the most recent export archive using `freelance import`:
   ```bash
   freelance import ~/.freelance/backups/JOB-001-20260916.tar.gz --replace
   ```

---

## 4. Archive Export & Migration (`freelance export` & `freelance import`)

To prevent data loss before major OS upgrades or client handoffs:
```bash
# Export active job with SHA-256 integrity verification
freelance export JOB-001 --output ~/backups/JOB-001.tar.gz

# Verify and safely restore into a clean workspace
freelance import ~/backups/JOB-001.tar.gz
```
The export archive includes:
- All job metadata, requirements, session logs, bug reports, and timeline events.
- `manifest.json` with file counts, export timestamp, and individual SHA-256 file hashes.
- Path sanitization to prevent archive extraction vulnerabilities.
