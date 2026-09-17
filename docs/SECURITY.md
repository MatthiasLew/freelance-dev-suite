# Security & Secret Hardening Guide

`freelance-dev-suite` manages commercial agreements, client codebase paths, and deliverables. To ensure robust security and confidentiality, the suite implements multi-layered protections.

---

## 1. Automated Secret Redaction (`packages/security/secrets.py`)

All text emitted through the CLI, generated in client messages, served via MCP, or written to handoff packages passes through `mask_text` to prevent accidental credential leakage.

### Detected and Redacted Patterns:
- **OpenAI API Keys**: `sk-...` -> `***MASKED_OPENAI_KEY***`
- **Anthropic API Keys**: `sk-ant-...` -> `***MASKED_ANTHROPIC_KEY***`
- **OpenRouter API Keys**: `sk-or-...` -> `***MASKED_OPENROUTER_KEY***`
- **GitHub Personal Access Tokens**: `ghp_...`, `gho_...`, `ghu_...`, `ghs_...`, `ghr_...` -> `***MASKED_GITHUB_TOKEN***`
- **Database Connection Strings**: `postgres://...`, `mysql://...`, `mongodb://...`, `redis://...` -> `***MASKED_CONNECTION_STRING***`
- **Private Key Blocks**: `-----BEGIN [A-Z ]*PRIVATE KEY-----...` -> `***MASKED_PRIVATE_KEY***`

---

## 2. Path Traversal & Jailbreak Guards (`assert_safe_path`)

When handling client repository paths, export targets, or import archives, `freelance-dev-suite` strictly checks destination paths:
- Enforces that resolved paths reside strictly within allowed parent directories.
- Disallows relative traversal vectors (`../`, `..\\`) that escape the workspace boundaries.
- Rejects absolute paths pointing outside authorized directories with `ValueError`.

---

## 3. Archive Safety & Zip Slip Prevention

During `freelance import`:
- Archive members are verified before extraction.
- Tarball member paths containing `..` or absolute drive root indicators (e.g. `C:\` or `/etc`) are immediately rejected.
- Symbolic links pointing outside the extraction root are discarded.

---

## 4. Atomic & Safe File Persistence

- File updates use sibling temporary files (`.tmp`) followed by atomic rename (`os.replace`) to prevent file corruption during sudden system termination or process kill.
- Process-level locking (`storage_lock`) with thread-local re-entrancy tracking prevents race conditions between parallel CLI processes.

