"""Deterministic requirements generator and bidirectional markdown parser."""

from __future__ import annotations

import re
from typing import Any

from .models import (
    AcceptanceCriterion,
    RequirementApprovalState,
    RequirementItem,
    RequirementsSpec,
)

# Section classification keyword heuristics
INPUT_KEYWORDS = {
    "pobierać",
    "pobiera",
    "pobieranie",
    "wczytać",
    "wczytuje",
    "odczyt",
    "load",
    "read",
    "input",
    "import",
    "csv",
    "json",
    "api input",
    "upload",
    "receive",
    "fetch",
    "datasource",
    "data source",
    "parametr",
    "request",
}

PROCESSING_KEYWORDS = {
    "usuwać",
    "usuwa",
    "usunąć",
    "duplikaty",
    "sortować",
    "sortuje",
    "sort",
    "filtrować",
    "filtr",
    "obliczać",
    "kalkulacja",
    "transformacja",
    "konwersja",
    "convert",
    "process",
    "parse",
    "clean",
    "validate",
    "sprawdzać",
    "walidacja",
    "deduplicate",
    "merge",
    "aggregate",
}

OUTPUT_KEYWORDS = {
    "generować",
    "generuje",
    "zapisywać",
    "zapisuje",
    "zapis",
    "export",
    "eksport",
    "wysyłać",
    "wysyła",
    "excel",
    "xlsx",
    "pdf",
    "raport",
    "report",
    "output",
    "save",
    "response",
    "endpoint",
    "view",
    "ui",
    "display",
    "tabela",
}


def _classify_requirement_section(text: str) -> str:
    """Classify a line or clause into an appropriate functional section."""
    lower = text.lower()
    in_score = sum(1 for kw in INPUT_KEYWORDS if kw in lower)
    proc_score = sum(1 for kw in PROCESSING_KEYWORDS if kw in lower)
    out_score = sum(1 for kw in OUTPUT_KEYWORDS if kw in lower)

    if in_score > proc_score and in_score > out_score:
        return "Input"
    if out_score > proc_score and out_score > in_score:
        return "Output"
    if proc_score > 0:
        return "Processing"
    if in_score > 0:
        return "Input"
    if out_score > 0:
        return "Output"
    return "General"


def _split_into_clauses(text: str) -> list[str]:
    """Split freeform text into distinct requirement clauses."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    raw_parts: list[str] = []

    for line in lines:
        # Strip markdown bullets or numbers
        cleaned = re.sub(r"^([*\-+•]|\d+[.)])\s*", "", line).strip()
        # Strip leading checkboxes if present
        cleaned = re.sub(r"^\[[ xX]\]\s*", "", cleaned).strip()
        if not cleaned:
            continue

        # Split on commas / semicolons if multiple clauses present
        if ("," in cleaned or ";" in cleaned) and not cleaned.startswith("http"):
            parts = re.split(r"[,;]+", cleaned)
            for p in parts:
                p_clean = p.strip()
                if p_clean:
                    raw_parts.append(p_clean)
        else:
            raw_parts.append(cleaned)

    clauses: list[str] = []
    all_keywords = INPUT_KEYWORDS | PROCESSING_KEYWORDS | OUTPUT_KEYWORDS

    for part in raw_parts:
        # Check if part has " i " or " and " joining two actions
        match = re.split(r"\s+(?:i|and)\s+", part, flags=re.IGNORECASE)
        if (
            len(match) > 1
            and all(len(m.strip()) > 3 for m in match)
            and any(any(kw in m.lower() for kw in all_keywords) for m in match)
        ):
            for m in match:
                m_clean = m.strip().rstrip(".").rstrip(",")
                if m_clean:
                    clauses.append(m_clean)
            continue

        p_clean = part.strip().rstrip(".").rstrip(",")
        if p_clean:
            clauses.append(p_clean)

    return clauses


def generate_requirements(
    text: str,
    job_id: str = "",
    title: str = "",
    intake_context: dict[str, Any] | None = None,
) -> RequirementsSpec:
    """Generate a structured RequirementsSpec from raw text and optional intake context."""
    clauses = _split_into_clauses(text)
    if not clauses and title:
        clauses = _split_into_clauses(title)

    requirements: list[RequirementItem] = []
    acceptance_criteria: list[AcceptanceCriterion] = []
    assumptions: list[str] = []
    out_of_scope: list[str] = []
    questions: list[str] = []

    # Map clauses to requirements
    req_index = 1
    for clause in clauses:
        section = _classify_requirement_section(clause)
        req_id = f"req-{req_index}"
        requirements.append(
            RequirementItem(
                id=req_id,
                title=clause,
                section=section,
                completed=False,
            )
        )
        req_index += 1

    # Generate default acceptance criteria based on sections found
    ac_index = 1
    sections_found = {r.section for r in requirements}

    if "Input" in sections_found:
        acceptance_criteria.append(
            AcceptanceCriterion(
                id=f"ac-{ac_index}",
                criterion=(
                    "Input data format and schema are validated "
                    "with clear error messages for invalid input."
                ),
                completed=False,
            )
        )
        ac_index += 1

    if "Processing" in sections_found:
        acceptance_criteria.append(
            AcceptanceCriterion(
                id=f"ac-{ac_index}",
                criterion=(
                    "All business logic transformations and data processing "
                    "operate accurately without data loss."
                ),
                completed=False,
            )
        )
        ac_index += 1

    if "Output" in sections_found:
        acceptance_criteria.append(
            AcceptanceCriterion(
                id=f"ac-{ac_index}",
                criterion=(
                    "Output files/responses are generated in the specified format "
                    "and open/parse cleanly."
                ),
                completed=False,
            )
        )
        ac_index += 1

    # General acceptance criterion
    acceptance_criteria.append(
        AcceptanceCriterion(
            id=f"ac-{ac_index}",
            criterion=(
                "Edge cases (empty data, unexpected characters, large inputs) "
                "do not crash the application."
            ),
            completed=False,
        )
    )

    # Standard assumptions
    assumptions.append("Input data uses standard UTF-8 encoding unless specified otherwise.")
    assumptions.append("Target environment has required runtime dependencies installed.")

    # Incorporate intake context if provided
    if intake_context:
        languages = intake_context.get("languages", [])
        if languages:
            assumptions.append(
                f"Implementation utilizes existing tech stack: {', '.join(languages)}."
            )
        if intake_context.get("has_docker"):
            assumptions.append("Deployment/execution supports Docker containerization.")

    # Default out of scope
    out_of_scope.append("Changes or extensions not explicitly listed in this specification.")
    out_of_scope.append("Custom multi-tenant cloud hosting infrastructure setup.")

    # Generate clarifying questions if text is short/ambiguous
    if len(clauses) <= 2:
        questions.append("Are there specific sample input files or test datasets available?")
        questions.append("What are the exact target environment and OS requirements?")

    return RequirementsSpec(
        job_id=job_id or "JOB-DRAFT",
        title=title or (clauses[0] if clauses else "Freelance Job Specification"),
        approval_state=RequirementApprovalState.DRAFT.value,
        requirements=requirements,
        acceptance_criteria=acceptance_criteria,
        assumptions=assumptions,
        out_of_scope=out_of_scope,
        questions=questions,
        unresolved_decisions=[],
    )


def parse_requirements_markdown(markdown_content: str, job_id: str = "") -> RequirementsSpec:
    """Parse a requirements markdown document back into a structured RequirementsSpec."""
    lines = markdown_content.splitlines()

    title = ""
    status = RequirementApprovalState.DRAFT.value
    version = 1
    created_at = ""
    updated_at = ""
    confirmed_at: str | None = None
    confirmed_by: str | None = None

    requirements: list[RequirementItem] = []
    acceptance_criteria: list[AcceptanceCriterion] = []
    assumptions: list[str] = []
    out_of_scope: list[str] = []
    questions: list[str] = []
    unresolved_decisions: list[str] = []

    current_main_section = ""
    current_sub_section = "General"
    req_counter = 1
    ac_counter = 1

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Header 1: # Requirements — JOB-001: Title
        if stripped.startswith("# "):
            header_text = stripped.lstrip("#").strip()
            match = re.match(r"Requirements\s*[-—–]\s*([^:]+):\s*(.*)", header_text, re.IGNORECASE)
            if match:
                job_id = match.group(1).strip()
                title = match.group(2).strip()
            else:
                title = header_text
            continue

        # Metadata extraction
        if stripped.startswith("**Status:**"):
            val = stripped.replace("**Status:**", "").replace("`", "").strip()
            if val in {s.value for s in RequirementApprovalState}:
                status = val
            continue

        if stripped.startswith("**Version:**"):
            val = stripped.replace("**Version:**", "").replace("v", "").strip()
            if val.isdigit():
                version = int(val)
            continue

        if stripped.startswith("**Created:**"):
            created_at = stripped.replace("**Created:**", "").strip()
            continue

        if stripped.startswith("**Last Updated:**"):
            updated_at = stripped.replace("**Last Updated:**", "").strip()
            continue

        if stripped.startswith("**Confirmed:**"):
            conf_line = stripped.replace("**Confirmed:**", "").strip()
            if "by" in conf_line:
                parts = conf_line.split("by", 1)
                confirmed_at = parts[0].strip()
                confirmed_by = parts[1].strip()
            else:
                confirmed_at = conf_line
            continue

        # Main sections (## Header)
        if stripped.startswith("## "):
            sec_name = stripped.lstrip("#").strip().lower()
            if "requirement" in sec_name or "implementation" in sec_name:
                current_main_section = "requirements"
                current_sub_section = "General"
            elif "acceptance" in sec_name:
                current_main_section = "acceptance"
            elif "assumption" in sec_name:
                current_main_section = "assumptions"
            elif "out of scope" in sec_name:
                current_main_section = "out_of_scope"
            elif "question" in sec_name:
                current_main_section = "questions"
            elif "decision" in sec_name:
                current_main_section = "unresolved_decisions"
            else:
                current_main_section = sec_name
            continue

        # Subsection for requirements (### Input)
        if stripped.startswith("### "):
            current_sub_section = stripped.lstrip("#").strip()
            continue

        # Checklist and bullet item parsing
        if stripped.startswith("- "):
            item_text = stripped[2:].strip()
            is_completed = False
            if item_text.startswith("[x]") or item_text.startswith("[X]"):
                is_completed = True
                item_text = item_text[3:].strip()
            elif item_text.startswith("[ ]"):
                is_completed = False
                item_text = item_text[3:].strip()

            if current_main_section == "requirements":
                # Check for explicit `req-1`: Title or [req-1] Title
                match_id = re.match(r"^[`\[]?([a-zA-Z0-9_\-]+)[`\]]?[:\-]\s*(.*)", item_text)
                if match_id:
                    item_id = match_id.group(1).strip()
                    item_title = match_id.group(2).strip()
                else:
                    item_id = f"req-{req_counter}"
                    item_title = item_text
                req_counter += 1

                # Extract notes if present _(note)_
                note = ""
                note_match = re.search(r"_\((.*?)\)_$", item_title)
                if note_match:
                    note = note_match.group(1).strip()
                    item_title = item_title[: note_match.start()].strip()

                requirements.append(
                    RequirementItem(
                        id=item_id,
                        title=item_title,
                        section=current_sub_section,
                        completed=is_completed,
                        notes=note,
                    )
                )

            elif current_main_section == "acceptance":
                match_id = re.match(r"^[`\[]?([a-zA-Z0-9_\-]+)[`\]]?[:\-]\s*(.*)", item_text)
                if match_id:
                    ac_id = match_id.group(1).strip()
                    crit = match_id.group(2).strip()
                else:
                    ac_id = f"ac-{ac_counter}"
                    crit = item_text
                ac_counter += 1

                acceptance_criteria.append(
                    AcceptanceCriterion(
                        id=ac_id,
                        criterion=crit,
                        completed=is_completed,
                    )
                )

            elif current_main_section == "assumptions":
                assumptions.append(item_text)
            elif current_main_section == "out_of_scope":
                out_of_scope.append(item_text)
            elif current_main_section == "questions":
                questions.append(item_text)
            elif current_main_section == "unresolved_decisions":
                unresolved_decisions.append(item_text)

    spec = RequirementsSpec(
        job_id=job_id or "JOB-DRAFT",
        title=title or "Requirements",
        approval_state=status,
        requirements=requirements,
        acceptance_criteria=acceptance_criteria,
        assumptions=assumptions,
        out_of_scope=out_of_scope,
        questions=questions,
        unresolved_decisions=unresolved_decisions,
        confirmed_at=confirmed_at,
        confirmed_by=confirmed_by,
        version=version,
    )
    if created_at:
        spec.created_at = created_at
    if updated_at:
        spec.updated_at = updated_at

    return spec
