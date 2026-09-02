"""Bug report processing, deterministic extraction, and file management."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import BugReport, BugSeverity, BugStatus


class BugProcessor:
    """Parses raw issue text, generates questions, and manages bug artifacts."""

    def parse_raw_report(
        self,
        raw_text: str,
        job_id: str,
        bug_id: str,
        title: str = "",
        severity: str = BugSeverity.MEDIUM.value,
    ) -> BugReport:
        """Deterministically parse unstructured client bug report."""
        text = raw_text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Determine Title
        if not title:
            if lines:
                first = lines[0]
                # If first line is a header or short sentence
                clean_first = re.sub(r"^[#\-\*0-9\.\s]+", "", first)
                title = clean_first[:60] if len(clean_first) <= 80 else clean_first[:60] + "..."
            else:
                title = "Reported issue"

        # 2. Extract Error Logs / Tracebacks
        error_logs = ""
        traceback_match = re.search(
            r"(Traceback \(most recent call last\):[\s\S]*?(?:\w+Error|\w+Exception):[^\n]+)",
            text,
        )
        if traceback_match:
            error_logs = traceback_match.group(1).strip()
        else:
            err_line_match = re.search(
                r"((?:Exception|Error|Fatal|Failed|HTTP [45]\d\d)[:\s][^\n]+)",
                text,
                re.IGNORECASE,
            )
            if err_line_match:
                error_logs = err_line_match.group(1).strip()

        # 3. Extract Steps to Reproduce
        steps: list[str] = []
        for line in lines:
            m_step = re.match(r"^(?:krok\s*)?[0-9]+[\.\)]\s*(.*)", line, re.IGNORECASE)
            if m_step and m_step.group(1):
                steps.append(m_step.group(1))

        # 4. Extract Expected vs Actual
        expected_behavior = ""
        actual_behavior = ""

        for line in lines:
            if re.search(r"\b(?:oczekiwan[eay]|expected|powinno)\b", line, re.IGNORECASE):
                expected_behavior = re.sub(
                    r"^.*?\b(?:oczekiwan[eay]|expected|powinno)[:\s]*",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()
            elif re.search(
                r"\b(?:faktyczn[eay]|actual|zamiast tego|błąd|error|wyskakuje)\b",
                line,
                re.IGNORECASE,
            ):
                actual_behavior = re.sub(
                    r"^.*?\b(?:faktyczn[eay]|actual|zamiast tego)[:\s]*",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()

        if not actual_behavior and error_logs:
            actual_behavior = f"Application crashes with: {error_logs.splitlines()[-1]}"

        # 5. Extract Environment Hints
        env: dict[str, str] = {}
        if re.search(r"\bwindows", text, re.IGNORECASE):
            env["OS"] = "Windows"
        elif re.search(r"\b(?:ubuntu|linux|debian)", text, re.IGNORECASE):
            env["OS"] = "Linux"
        elif re.search(r"\b(?:mac|macos|darwin)", text, re.IGNORECASE):
            env["OS"] = "macOS"

        py_ver = re.search(r"\bpython\s*([23]\.\d+)", text, re.IGNORECASE)
        if py_ver:
            env["Python"] = py_ver.group(1)

        # 6. Generate Clarifying Questions for Client
        questions: list[str] = []
        if not steps:
            questions.append(
                "Jakie dokładnie kroki wykonujesz przed wystąpieniem błędu? "
                "(np. 1. Klikam X, 2. Wpisuję Y...)"
            )
        if not error_logs and re.search(
            r"\b(?:błąd|error|nie działa|crash)\b", text, re.IGNORECASE
        ):
            questions.append(
                "Czy pojawia się dokładna treść błędu / zrzut ekranu lub plik z logami?"
            )
        if not env:
            questions.append(
                "Na jakim systemie operacyjnym (Windows / Linux / macOS) "
                "oraz w jakim środowisku uruchamiasz program?"
            )
        if not expected_behavior:
            questions.append(
                "Jakiego dokładnego rezultatu oczekujesz po wykonaniu tej akcji?"
            )

        # 7. Initial Status
        status = (
            BugStatus.NEEDS_INFO.value
            if (len(questions) >= 2 and not steps)
            else BugStatus.REPORTED.value
        )

        return BugReport(
            id=bug_id,
            job_id=job_id,
            title=title,
            raw_description=text,
            status=status,
            severity=severity,
            steps_to_reproduce=steps,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            environment=env,
            error_logs=error_logs,
            questions_for_client=questions,
        )

    def next_bug_id(self, job_dir: Path) -> str:
        """Generate next sequential bug ID: BUG-001, BUG-002, etc."""
        bugs_dir = job_dir / "work" / "bugs"
        if not bugs_dir.exists():
            return "BUG-001"

        highest = 0
        for p in bugs_dir.glob("BUG-*.json"):
            m = re.match(r"^BUG-(\d+)\.json$", p.name)
            if m:
                highest = max(highest, int(m.group(1)))

        return f"BUG-{highest + 1:03d}"

    def save_bug(self, bug: BugReport, job_dir: Path) -> dict[str, Path]:
        """Persist bug JSON, Markdown summary, questions doc, and reproduction script."""
        bugs_dir = job_dir / "work" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        paths: dict[str, Path] = {}

        # 1. JSON Data
        json_path = bugs_dir / f"{bug.id}.json"
        json_path.write_text(
            json.dumps(bug.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths["json"] = json_path

        # 2. Markdown Summary
        summary_path = bugs_dir / f"{bug.id}-summary.md"
        summary_path.write_text(bug.to_markdown(), encoding="utf-8")
        paths["summary"] = summary_path

        # 3. Questions doc
        if bug.questions_for_client:
            q_path = bugs_dir / f"{bug.id}-questions-for-client.md"
            q_path.write_text(bug.to_questions_markdown(), encoding="utf-8")
            paths["questions"] = q_path

        # 4. Reproduction script
        repro_path = bugs_dir / f"{bug.id}-repro.py"
        if not repro_path.exists():
            repro_path.write_text(bug.to_repro_script(), encoding="utf-8")
        paths["repro"] = repro_path

        return paths

    def load_bug(self, job_dir: Path, bug_id: str) -> BugReport | None:
        """Load a bug by its ID from job work/bugs directory."""
        clean_id = bug_id.upper()
        json_path = job_dir / "work" / "bugs" / f"{clean_id}.json"
        if not json_path.exists():
            return None

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            return BugReport.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def list_bugs(self, job_dir: Path) -> list[BugReport]:
        """List all bug reports in the job work/bugs directory."""
        bugs_dir = job_dir / "work" / "bugs"
        if not bugs_dir.exists():
            return []

        bugs: list[BugReport] = []
        for p in sorted(bugs_dir.glob("BUG-*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    bugs.append(BugReport.from_dict(json.load(f)))
            except (OSError, json.JSONDecodeError):
                continue

        return bugs
