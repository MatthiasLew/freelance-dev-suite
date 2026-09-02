"""Message generation engine for freelance client communication."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import ClientMessage, MessageStage


class MessageGenerator:
    """Generates context-aware, polished client communication messages."""

    def generate(
        self,
        job_id: str,
        job_dir: Path,
        stage: MessageStage | str,
        language: str = "pl",
        notes: str = "",
    ) -> ClientMessage:
        """Generate tailored message based on project state and stage."""
        stage_val = stage.value if isinstance(stage, MessageStage) else str(stage).lower()
        client_name = "Klient" if language == "pl" else "Client"
        project_title = f"Projekt {job_id}"

        # 1. Load job.json
        job_file = job_dir / "job.json"
        if job_file.exists():
            try:
                with open(job_file, encoding="utf-8") as f:
                    job_data = json.load(f)
                client_name = str(job_data.get("client", client_name))
                desc = str(job_data.get("description", ""))
                if desc:
                    project_title = desc[:50]
            except (OSError, json.JSONDecodeError):
                pass

        # 2. Load estimate if available
        quote_price = 0.0
        quote_hours = 0.0
        est_file = job_dir / "analysis" / "estimate.json"
        if est_file.exists():
            try:
                with open(est_file, encoding="utf-8") as f:
                    est_data = json.load(f)
                quote_price = float(est_data.get("price_pln", 0.0))
                quote_hours = float(est_data.get("hours", 0.0))
            except (OSError, json.JSONDecodeError):
                pass

        # 3. Load requirements if available
        req_count = 0
        req_titles: list[str] = []
        req_file = job_dir / "analysis" / "requirements.json"
        if req_file.exists():
            try:
                with open(req_file, encoding="utf-8") as f:
                    req_data = json.load(f)
                for r in req_data.get("requirements", []):
                    req_titles.append(str(r.get("title", "")))
                req_count = len(req_titles)
            except (OSError, json.JSONDecodeError):
                pass

        # 4. Generate Body according to stage & language
        if stage_val in (MessageStage.INTAKE.value, "welcome"):
            subject, body = self._generate_intake(
                client_name, project_title, req_titles, language, notes
            )
        elif stage_val in (MessageStage.QUOTE.value, "proposal"):
            subject, body = self._generate_quote(
                client_name, project_title, quote_price, quote_hours, language, notes
            )
        elif stage_val in (MessageStage.UPDATE.value, "milestone"):
            subject, body = self._generate_update(
                client_name, project_title, req_count, language, notes
            )
        elif stage_val == MessageStage.DEMO.value:
            subject, body = self._generate_demo(
                client_name, project_title, language, notes
            )
        elif stage_val in (MessageStage.DELIVERY.value, "handoff"):
            subject, body = self._generate_delivery(
                client_name, project_title, language, notes
            )
        elif stage_val == MessageStage.REMINDER.value:
            subject, body = self._generate_reminder(
                client_name, project_title, language, notes
            )
        elif stage_val == MessageStage.SCOPE_NOTICE.value:
            subject, body = self._generate_scope_notice(
                client_name, project_title, language, notes
            )
        else:
            subject, body = self._generate_update(
                client_name, project_title, req_count, language, notes
            )

        msg = ClientMessage(
            job_id=job_id,
            client_name=client_name,
            stage=stage_val,
            subject=subject,
            body=body,
            language=language,
        )

        # 5. Persist message draft
        messages_dir = job_dir / "work" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg_file = messages_dir / f"MSG_{ts}_{stage_val}.md"
        msg_file.write_text(msg.to_markdown(), encoding="utf-8")

        return msg

    def _generate_intake(
        self, client: str, title: str, reqs: list[str], lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Potwierdzenie przyjęcia briefu — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Dziękuję za przesłanie materiałów dotyczących projektu: **{title}**.",
                (
                    "Przeanalizowałem wstępne założenia i przygotowuję specyfikację techniczną "
                    "oraz harmonogram."
                ),
            ]
            if reqs:
                body_lines.extend([
                    "",
                    "Główne punkty, które wyodrębniłem z Twojego zgłoszenia:",
                    *[f"- {r}" for r in reqs[:4]],
                ])
            if notes:
                body_lines.extend(["", f"Uwagi/Pytania: {notes}"])
            body_lines.extend([
                "",
                "W kolejnym kroku prześlę podsumowanie zakresu i wycenę.",
                "",
                "Pozdrawiam serdecznie,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Project Kickoff & Brief Received — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"Thank you for sharing the project brief for: **{title}**.",
            (
                "I have reviewed the initial requirements and am preparing the technical scope "
                "and timeline."
            ),
        ]
        if reqs:
            body_lines.extend([
                "",
                "Key elements captured from your description:",
                *[f"- {r}" for r in reqs[:4]],
            ])
        if notes:
            body_lines.extend(["", f"Notes / Questions: {notes}"])
        body_lines.extend([
            "",
            "I will follow up shortly with a detailed scope confirmation and quote.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

    def _generate_quote(
        self, client: str, title: str, price: float, hours: float, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Oferta i wycena realizacji — {title}"
            if price > 0:
                price_str = f"- **Wycena całkowita:** {price:.0f} PLN netto"
            else:
                price_str = "- **Wycena:** Według ustaleń"
            hours_str = f"- **Szacowany czas:** {hours:.1f}h" if hours > 0 else ""
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Przygotowałem szczegółową wycenę oraz plan realizacji projektu: **{title}**.",
                "",
                price_str,
                hours_str,
                "",
                "Wycena obejmuje:",
                "- Pełną implementację zgodnie z zaakceptowaną specyfikacją,",
                "- Zestaw automatycznych testów jednostkowych i integracyjnych,",
                "- Kompletną dokumentację wdrożeniową i instrukcję użytkownika,",
                "- Raport Final Quality Gate potwierdzający stabilność i brak regresji.",
            ]
            if notes:
                body_lines.extend(["", f"Szczegóły: {notes}"])
            body_lines.extend([
                "",
                "Jeśli propozycja Ci odpowiada, możemy natychmiast rozpocząć prace wdrożeniowe.",
                "",
                "Pozdrawiam,",
            ])
            return subject, "\n".join([b for b in body_lines if b])

        subject = f"Project Proposal & Estimate — {title}"
        if price > 0:
            price_str_en = f"- **Total Estimate:** {price:.0f} PLN"
        else:
            price_str_en = "- **Estimate:** As discussed"
        hours_str_en = f"- **Estimated Effort:** {hours:.1f} hours" if hours > 0 else ""
        body_lines = [
            f"Hi {client},",
            "",
            f"I have prepared the proposal and implementation quote for: **{title}**.",
            "",
            price_str_en,
            hours_str_en,
            "",
            "The quote includes:",
            "- Complete implementation based on agreed requirements,",
            "- Automated test suite ensuring zero regressions,",
            "- Comprehensive user guide and installation documentation,",
            "- Final Quality Gate verification.",
        ]
        if notes:
            body_lines.extend(["", f"Details: {notes}"])
        body_lines.extend([
            "",
            "Looking forward to your feedback so we can kick off implementation.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join([b for b in body_lines if b])

    def _generate_update(
        self, client: str, title: str, req_count: int, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Status postępu prac — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Krótka aktualizacja dotycząca postępów w projekcie: **{title}**.",
                "Prace przebiegają zgodnie z planem i harmonogramem.",
            ]
            if notes:
                body_lines.extend(["", f"Ostatnie wdrożenia: {notes}"])
            body_lines.extend([
                "",
                "Wkrótce przekażę wersję do pierwszych testów.",
                "",
                "Pozdrawiam,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Project Progress Update — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"Here is a quick progress update on: **{title}**.",
            "Development is proceeding on schedule.",
        ]
        if notes:
            body_lines.extend(["", f"Recent accomplishments: {notes}"])
        body_lines.extend([
            "",
            "I will share a testing build shortly.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

    def _generate_demo(
        self, client: str, title: str, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Wersja testowa gotowa do wglądu — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Przygotowałem wersję demonstracyjną/testową projektu: **{title}**.",
                (
                    "Wszystkie zaplanowane funkcje zostały zaimplementowane "
                    "i pomyślnie przeszły testy techniczne."
                ),
            ]
            if notes:
                body_lines.extend(["", f"Instrukcja dostępu / Uwagi: {notes}"])
            body_lines.extend([
                "",
                "Będę wdzięczny za Twoją weryfikację i uwagi przed finalnym zamknięciem projektu.",
                "",
                "Pozdrawiam,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Demo / Staging Build Ready for Review — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"A working demo / build is now ready for your review: **{title}**.",
            "All specified features are implemented and validated by automated tests.",
        ]
        if notes:
            body_lines.extend(["", f"Access details / Notes: {notes}"])
        body_lines.extend([
            "",
            "Please review when convenient and let me know if you have any feedback.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

    def _generate_delivery(
        self, client: str, title: str, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Finalna dostawa projektu — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Z przyjemnością przekazuję finalną paczkę projektu: **{title}**.",
                (
                    "Projekt przeszedł 100% testów jakości Quality Gate "
                    "i jest gotowy do produkcyjnego użycia."
                ),
                "",
                "Paczka zawiera:",
                "- Kompletny kod źródłowy oraz archiwum wydania,",
                "- Instrukcję instalacji i uruchomienia (`INSTALLATION.md`),",
                "- Podręcznik użytkownika (`USER_GUIDE.md`),",
                "- Raport testów i potwierdzenie zgodności z wymaganiami.",
            ]
            if notes:
                body_lines.extend(["", f"Dodatkowe informacje: {notes}"])
            body_lines.extend([
                "",
                "Dziękuję za doskonałą współpracę! Będę wdzięczny za krótką opinię lub referencje.",
                "",
                "Pozdrawiam serdecznie,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Final Project Delivery & Handoff — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"I am pleased to deliver the final release package for: **{title}**.",
            "The project has passed all Quality Gate checks and is ready for production.",
            "",
            "The deliverable package contains:",
            "- Full clean source code and release archive,",
            "- Installation and configuration guide (`INSTALLATION.md`),",
            "- User manual (`USER_GUIDE.md`),",
            "- Test report and requirements traceability matrix.",
        ]
        if notes:
            body_lines.extend(["", f"Additional notes: {notes}"])
        body_lines.extend([
            "",
            (
                "Thank you for the great collaboration! "
                "A brief review or testimonial would be greatly appreciated."
            ),
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

    def _generate_reminder(
        self, client: str, title: str, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Uprzejme przypomnienie — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"Pozwalam sobie na krótkie przypomnienie w sprawie projektu: **{title}**.",
            ]
            if notes:
                body_lines.extend(["", f"Dotyczy: {notes}"])
            else:
                body_lines.extend([
                    (
                        "Będę wdzięczny za informację zwrotną dotyczącą statusu "
                        "akceptacji lub płatności."
                    )
                ])
            body_lines.extend([
                "",
                "W razie jakichkolwiek pytań pozostaję do dyspozycji.",
                "",
                "Pozdrawiam,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Gentle Reminder — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"Just a friendly follow-up regarding: **{title}**.",
        ]
        if notes:
            body_lines.extend(["", f"Details: {notes}"])
        else:
            body_lines.extend([
                (
                    "Please let me know if you need any assistance or have "
                    "feedback on the deliverables."
                )
            ])
        body_lines.extend([
            "",
            "Thank you and looking forward to hearing from you.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

    def _generate_scope_notice(
        self, client: str, title: str, lang: str, notes: str
    ) -> tuple[str, str]:
        if lang == "pl":
            subject = f"Informacja o zakresie zlecenia — {title}"
            body_lines = [
                f"Dzień dobry {client},",
                "",
                f"W nawiązaniu do ostatniej prośby o zmiany w projekcie: **{title}**.",
                (
                    "Zidentyfikowałem, że wnioskowane modyfikacje wykraczają "
                    "poza pierwotnie zaakceptowaną specyfikację."
                ),
            ]
            if notes:
                body_lines.extend(["", f"Wycena i zakres: {notes}"])
            body_lines.extend([
                "",
                (
                    "Przygotowałem propozycję aneksu rozszerzającego zakres prac. "
                    "Daj znać, jak chcesz postąpić."
                ),
                "",
                "Pozdrawiam,",
            ])
            return subject, "\n".join(body_lines)

        subject = f"Scope Extension Notice — {title}"
        body_lines = [
            f"Hi {client},",
            "",
            f"Regarding your recent request for: **{title}**.",
            "I noted that these changes extend beyond our original agreed scope.",
        ]
        if notes:
            body_lines.extend(["", f"Scope & estimate: {notes}"])
        body_lines.extend([
            "",
            "I have prepared a change order proposal. Let me know how you would like to proceed.",
            "",
            "Best regards,",
        ])
        return subject, "\n".join(body_lines)

