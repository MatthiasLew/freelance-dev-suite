# Security & Secret Hardening Guide

`freelance-dev-suite` manages commercial agreements, client codebase paths, and deliverables. To ensure enterprise-grade security and confidentiality, the suite implements multi-layered protections.

---

## 1. Automated Secret Redaction (`packages/security/secrets.py`)

All text emitted through the CLI, generated in client messages, served via MCP, or written to handoff packages passes through `mask_text` to prevent accidental credential leakage.

### Detected and Redacted Patterns:
- **OpenAI API Keys**: `sk-[A-Za-z0-9]{20,T3BlbkFJ[A-Za-z0-9]{20,}}` -> `[REDACTED-OPENAI-KEY]`
- **Anthropic API Keys**: `sk-ant-[A-Za-z0-9_-]{20,}` -> `[REDACTED-ANTHROPIC-KEY]`
- **OpenRouter API Keys**: `sk-or-[A-Za-z0-9_-]{20,}` -> `[REDACTED-OPENROUTER-KEY]`
- **GitHub Personal Access Tokens**: `ghp_...`, `gho_...`, `ghu_...`, `ghs_...`, `ghr_...` -> `[REDACTED-GITHUB-TOKEN]`
- **Database Connection Strings**: `postgres://...`, `mysql://...`, `mongodb://...` -> Redacts embedded password credentials.
- **Private Key Blocks**: `-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----...` -> `[REDACTED-PRIVATE-KEY]`

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

- File updates use temporary files (`.tmp`) followed by atomic rename (`os.replace`) to prevent file corruption during sudden system termination or process kill.
- Sensitive state files are written with restricted file permissions on POSIX systems (`0o600` / `0o700`).
- Process-level locking (`storage_lock`) prevents race conditions between parallel CLI processes.
