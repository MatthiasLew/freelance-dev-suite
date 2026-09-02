"""Scope change detector, diff analyzer, and client proposal generator."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .models import ScopeChangeItem, ScopeClassification

if TYPE_CHECKING:
    from packages.requirements.models import RequirementsSpec


BREAKING_KEYWORDS = [
    r"\bprzepisz\b",
    r"\brewrite\b",
    r"\bzmie[nń]\s+baz[eę]\b",
    r"\bzmiana\s+architektur[ye]\b",
    r"\bmikroserwis",
    r"\bmicroservices\b",
    r"\bprzej[sś]cie\s+na\b",
    r"\bzamiast\s+python\b",
    r"\bzamiast\s+c#\b",
]

MINOR_KEYWORDS = [
    r"\bdrobn[eay]\b",
    r"\bkolor\b",
    r"\bnapis\b",
    r"\btekst\b",
    r"\betykiet[aęy]\b",
    r"\bformatowan",
    r"\bkolumn[aęy]\b",
    r"\bliter[oó]wk",
]


def _clean_stem(word: str) -> str:
    """Normalize Polish and English word stems."""
    return (
        word.lower()
        .replace("ą", "a")
        .replace("ć", "c")
        .replace("ę", "e")
        .replace("ł", "l")
        .replace("ń", "n")
        .replace("ó", "o")
        .replace("ś", "s")
        .replace("ź", "z")
        .replace("ż", "z")
    )[:4]


def _extract_stems(text: str) -> set[str]:
    """Extract 4-letter normalized stems from text."""
    words = re.findall(r"\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{3,}\b", text)
    stems = {_clean_stem(w) for w in words}

    # Add synonym expansions
    syn_map = {
        "logi": {"auth", "logi", "logw", "user", "uzyt"},
        "logw": {"auth", "logi", "logw", "user", "uzyt"},
        "uzyt": {"user", "uzyt", "clie"},
        "user": {"user", "uzyt", "clie"},
        "auth": {"auth", "logi", "logw", "jwtt"},
        "hasl": {"pass", "hasl"},
        "pass": {"pass", "hasl"},
        "emai": {"emai", "mail"},
        "mail": {"emai", "mail"},
        "eksp": {"eksp", "expo"},
        "expo": {"eksp", "expo"},
        "impo": {"impo", "wczy"},
    }
    expanded = set(stems)
    for s in stems:
        if s in syn_map:
            expanded.update(syn_map[s])
    return expanded


class ScopeChangeDetector:
    """Compares new client requests against approved requirements spec."""

    def analyze_request(
        self,
        job_id: str,
        change_id: str,
        requested_text: str,
        requirements_spec: RequirementsSpec | None,
        hourly_rate_pln: float = 150.0,
    ) -> ScopeChangeItem:
        """Analyze client request against scope baseline."""
        text = requested_text.strip()
        matched_reqs: list[str] = []
        new_features: list[str] = []

        # 1. Check if Breaking Change
        is_breaking = any(re.search(pat, text, re.IGNORECASE) for pat in BREAKING_KEYWORDS)
        if is_breaking:
            classification = ScopeClassification.BREAKING_CHANGE.value
            hours = 12.0
            ai_cost = 45.0
            impact = "Prośba wymaga istotnej zmiany architektury lub technologii projektu."
            new_features.append(text)
        elif requirements_spec is None or not requirements_spec.requirements:
            # No baseline to compare against
            classification = ScopeClassification.OUT_OF_SCOPE.value
            hours = 3.0
            ai_cost = 12.0
            impact = "Brak zatwierdzonej specyfikacji wymagań — traktowane jako nowy zakres."
            new_features.append(text)
        else:
            # Extract request stems
            req_stems = _extract_stems(text)

            # Check matching against existing requirements
            for item in requirements_spec.requirements:
                item_text = f"{item.title} {item.notes}"
                item_stems = _extract_stems(item_text)
                overlap = req_stems.intersection(item_stems)
                if len(overlap) >= 2 or (len(overlap) == 1 and len(req_stems) <= 3):
                    matched_reqs.append(f"{item.id}: {item.title}")

            for crit in requirements_spec.acceptance_criteria:
                crit_stems = _extract_stems(crit.criterion)
                overlap = req_stems.intersection(crit_stems)
                if len(overlap) >= 2:
                    matched_reqs.append(f"AC {crit.id}: {crit.criterion[:40]}")

            # Check if minor tweak
            is_minor = any(re.search(pat, text, re.IGNORECASE) for pat in MINOR_KEYWORDS)
            has_new_intent = bool(
                re.search(
                    r"\b(?:dodaj|now[aey]|nowy\s+moduł|eksport|integracj)\b",
                    text,
                    re.IGNORECASE,
                )
            )

            if is_minor and matched_reqs:
                classification = ScopeClassification.MINOR_EXTENSION.value
                hours = 1.0
                ai_cost = 4.0
                impact = "Drobne rozszerzenie lub modyfikacja istniejącego elementu."
                new_features.append(text)
            elif matched_reqs and not has_new_intent:
                classification = ScopeClassification.IN_SCOPE.value
                hours = 0.0
                ai_cost = 0.0
                impact = "Zgłoszenie w całości mieści się w ustalonym zakresie wymagań projektu."
            else:
                classification = ScopeClassification.OUT_OF_SCOPE.value
                # Estimate hours based on length and keywords
                if re.search(r"\b(?:eksport|pdf|excel|csv)\b", text, re.IGNORECASE):
                    hours = 3.0
                elif re.search(
                    r"\b(?:płatnoś|stripe|payu|auth|logowan|email|powiadom)\b",
                    text,
                    re.IGNORECASE,
                ):
                    hours = 4.5
                else:
                    hours = 2.5
                ai_cost = round(hours * 4.0, 2)
                impact = "Nowa funkcjonalność wykraczająca poza pierwotnie zaakceptowany zakres."
                new_features.append(text)

        # Calculate suggested price
        raw_price = (hours * hourly_rate_pln) + ai_cost
        # Round up to nearest 50 PLN if > 0
        suggested_price = float(int((raw_price + 49) // 50) * 50) if raw_price > 0 else 0.0

        # Generate polite client proposal
        proposal_msg = self._generate_proposal_message(
            change_id=change_id,
            requested_text=text,
            classification=classification,
            hours=hours,
            price_pln=suggested_price,
            matched_reqs=matched_reqs,
        )

        return ScopeChangeItem(
            id=change_id,
            job_id=job_id,
            requested_text=text,
            classification=classification,
            matched_existing_requirements=matched_reqs,
            new_functionalities=new_features,
            estimated_additional_hours=hours,
            estimated_ai_cost_pln=ai_cost,
            suggested_extra_price_pln=suggested_price,
            impact_assessment=impact,
            client_proposal_message=proposal_msg,
        )

    def _generate_proposal_message(
        self,
        change_id: str,
        requested_text: str,
        classification: str,
        hours: float,
        price_pln: float,
        matched_reqs: list[str],
    ) -> str:
        """Generate client-friendly message / change order proposal."""
        if classification == ScopeClassification.IN_SCOPE.value:
            req_info = ", ".join(matched_reqs) if matched_reqs else "ustalenia początkowe"
            return f"""Dzień dobry!

Przeanalizowałem Twoją prośbę dotyczącą:
> "{requested_text}"

Ta funkcjonalność mieści się w naszym pierwotnie uzgodnionym zakresie zlecenia
(powiązana z: {req_info}).
Zrealizuję ją bez żadnych dodatkowych opłat w ramach bieżącego projektu.

Pozdrawiam!
"""

        if classification == ScopeClassification.MINOR_EXTENSION.value:
            return f"""Dzień dobry!

W nawiązaniu do prośby:
> "{requested_text}"

Jest to drobna modyfikacja wykraczająca poza pierwotne ustalenia. 
Mogę wdrożyć tę zmianę od ręki:
- **Szacowany czas realizacji:** {hours:.1f}h
- **Koszt dodatkowy:** {price_pln:.0f} PLN netto

Jeśli akceptujesz taką wycenę, dodam ten punkt do bieżącej realizacji. Daj proszę znać!

Pozdrawiam!
"""

        if classification == ScopeClassification.BREAKING_CHANGE.value:
            return f"""Dzień dobry!

W nawiązaniu do przesłanej prośby:
> "{requested_text}"

Przeanalizowałem tę zmianę — wymaga ona gruntownej modyfikacji
dotychczasowej architektury i założeń technicznych projektu.
- **Szacowany dodatkowy nakład pracy:** ~{hours:.1f}h
- **Proponowana kwota dopłaty / aneksu:** {price_pln:.0f} PLN netto

Proponuję krótką rozmowę lub potwierdzenie mailowe, czy wdrażamy ten aneks do projektu.

Pozdrawiam!
"""

        # OUT_OF_SCOPE default
        return f"""Dzień dobry!

Dziękuję za wiadomość! Przeanalizowałem prośbę o dodanie:
> "{requested_text}"

Jest to nowa funkcjonalność, która wykracza poza pierwotnie zaakceptowaną
specyfikację wymagań projektu.
Z przyjemnością wdrożę dla Ciebie to rozszerzenie w ramach bieżącego projektu.

### Wycena rozszerzenia ({change_id}):
- **Zakres:** {requested_text}
- **Szacowany czas realizacji:** ~{hours:.1f}h roboczych
- **Sugerowana dopłata:** {price_pln:.0f} PLN netto

Jeśli warunki Ci odpowiadają, proszę o krótkie potwierdzenie i dopisuję to zadanie.

Pozdrawiam!
"""

    def next_change_id(self, job_dir: Path) -> str:
        """Generate next sequential change ID: CHANGE-001, CHANGE-002, etc."""
        scope_dir = job_dir / "work" / "scope"
        if not scope_dir.exists():
            return "CHANGE-001"

        highest = 0
        for p in scope_dir.glob("CHANGE-*.json"):
            m = re.match(r"^CHANGE-(\d+)\.json$", p.name)
            if m:
                highest = max(highest, int(m.group(1)))

        return f"CHANGE-{highest + 1:03d}"

    def save_change(self, item: ScopeChangeItem, job_dir: Path) -> dict[str, Path]:
        """Persist scope change analysis, proposal, and JSON data."""
        scope_dir = job_dir / "work" / "scope"
        scope_dir.mkdir(parents=True, exist_ok=True)

        paths: dict[str, Path] = {}

        # 1. JSON
        json_path = scope_dir / f"{item.id}.json"
        json_path.write_text(
            json.dumps(item.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        paths["json"] = json_path

        # 2. Analysis MD
        analysis_path = scope_dir / f"{item.id}-analysis.md"
        analysis_path.write_text(item.to_markdown(), encoding="utf-8")
        paths["analysis"] = analysis_path

        # 3. Proposal MD
        proposal_path = scope_dir / f"{item.id}-proposal.md"
        proposal_path.write_text(item.to_proposal_markdown(), encoding="utf-8")
        paths["proposal"] = proposal_path

        return paths

    def load_change(self, job_dir: Path, change_id: str) -> ScopeChangeItem | None:
        """Load scope change item by ID."""
        clean_id = change_id.upper()
        json_path = job_dir / "work" / "scope" / f"{clean_id}.json"
        if not json_path.exists():
            return None

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            return ScopeChangeItem.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def list_changes(self, job_dir: Path) -> list[ScopeChangeItem]:
        """List all scope changes in job work/scope directory."""
        scope_dir = job_dir / "work" / "scope"
        if not scope_dir.exists():
            return []

        changes: list[ScopeChangeItem] = []
        for p in sorted(scope_dir.glob("CHANGE-*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    changes.append(ScopeChangeItem.from_dict(json.load(f)))
            except (OSError, json.JSONDecodeError):
                continue

        return changes

    def create_snapshot(self, job_dir: Path, requirements_spec: RequirementsSpec) -> Path:
        """Save a frozen baseline snapshot of the current requirements spec."""
        snapshots_dir = job_dir / "analysis" / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = snapshots_dir / f"requirements_baseline_{timestamp}.json"
        snapshot_file.write_text(
            json.dumps(requirements_spec.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return snapshot_file
