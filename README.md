# Freelance Dev Suite

CLI toolkit for managing freelance development jobs — from intake and estimation through implementation to client handoff.

## Problem

Freelance developers waste time on:
- Analyzing unfamiliar projects before quoting
- Underestimating AI costs and work hours
- Scope creep after price agreement
- Missing quality checks before delivery
- Assembling handoff packages manually

**Freelance Dev Suite** automates the entire job lifecycle with one CLI.

## Install

```bash
pip install freelance-dev-suite
```

For development:

```bash
git clone https://github.com/MatthiasLew/freelance-dev-suite.git
cd freelance-dev-suite
pip install -e ".[dev]"
```

## Quick Start

```bash
# Create a new job
freelance job new

# List active jobs
freelance jobs

# Check job status
freelance status JOB-001
```

## Commands

| Command | Description | Status |
|---|---|---|
| `freelance job new` | Create a new job | ✅ implemented |
| `freelance jobs` | List all active jobs | ✅ implemented |
| `freelance status <JOB-ID>` | Show job details | ✅ implemented |
| `freelance analyze <JOB-ID>` | Run scan, validation, context, and AI-cost analysis | ✅ implemented |
| `freelance estimate <JOB-ID>` | Generate and persist a full quote | ✅ implemented |
| `freelance requirements <JOB-ID>` | Create requirements checklist | 🔜 planned |
| `freelance start <JOB-ID>` | Bootstrap project | 🔜 planned |
| `freelance bug add <JOB-ID>` | Add bug report | 🔜 planned |
| `freelance scope check <JOB-ID>` | Detect scope changes | 🔜 planned |
| `freelance handoff <JOB-ID>` | Run final QA | 🔜 planned |
| `freelance finish <JOB-ID>` | Close and archive job | 🔜 planned |

## Integration with ai-dev-cli-tools

This project uses [ai-dev-cli-tools](https://github.com/MatthiasLew/ai-dev-cli-tools) as the technical engine for:
- Project scanning and stack detection
- Test execution and linting
- Diagnostics and context building
- Bootstrap and final checks

Install with AI dev tools integration:

```bash
pip install "freelance-dev-suite[ai-dev]"
```

`freelance analyze` fails with a clear error when the engine is unavailable. During local
cross-repository development, point it at a source checkout executable:

```powershell
$env:AI_DEV_EXECUTABLE = "C:\path\to\ai-dev-cli-tools\.venv\Scripts\ai-dev.exe"
```

Analysis runs `scan`, `map`, `check`, and `context build`. Use `--check-mode fast` when a preview
without the complete validation suite is sufficient. Both MVP commands support structured output:

```bash
freelance analyze JOB-001 --json
freelance estimate JOB-001 --json
```

## Pricing configuration

Provider prices and the USD/PLN rate are assumptions, not live market data. The package contains a
reviewable default pricing snapshot. A user configuration may select another model, pricing file,
and exchange rate:

```yaml
models:
  default: claude-sonnet-4
  pricing_file: C:/freelance/model-pricing.yaml

exchange_rates:
  usd_to_pln: 4.0
```

The external pricing file uses a top-level `models` mapping with separate input, output, cached
input, and optional reasoning prices per million tokens.

## Architecture

```
ZLECENIE → intake → estimate → requirements → bootstrap → IMPLEMENTACJA → handoff → DONE
```

Freelance Dev Suite is the **business/workflow layer** on top of `ai-dev-cli-tools` (technical engine).

## License

MIT
