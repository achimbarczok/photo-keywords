"""AntwortValidator – Validiert geparste Ollama-Antworten auf Stichwortlisten-Qualität."""

from __future__ import annotations

from photo_keywords.models import ValidierungsConfig, ValidierungsErgebnis


class AntwortValidator:
    """Validiert geparste Ollama-Antworten auf Stichwortlisten-Qualität."""

    ABLEHNUNGS_PHRASEN: list[str] = [
        "ich kann nicht",
        "ich kann das nicht",
        "i cannot",
        "i can't",
        "i'm sorry",
        "es tut mir leid",
        "nicht möglich",
        "unable to",
        "i'm unable",
        "kann ich nicht",
        "leider kann",
        "leider nicht",
        "sorry",
    ]

    def __init__(self, config: ValidierungsConfig) -> None:
        self._config = config

    def validieren(self, keywords: list[str]) -> ValidierungsErgebnis:
        """Prüft ob die Stichwortliste gültig ist.

        Prüfreihenfolge:
        1. Leere Liste → ungültig
        2. Ablehnungsphrase in einem Eintrag → ungültig
        3. Einzeleintrag mit zu vielen Wörtern → ungültig
        4. Durchschnittliche Wortanzahl zu hoch → ungültig
        5. Sonst → gültig
        """
        if not keywords:
            return ValidierungsErgebnis(gueltig=False, grund="Leere Antwortliste")

        for eintrag in keywords:
            phrase = self._enthaelt_ablehnungs_phrase(eintrag)
            if phrase is not None:
                return ValidierungsErgebnis(
                    gueltig=False,
                    grund=f"Ablehnungsphrase erkannt: \"{phrase}\"",
                )

        if len(keywords) == 1:
            wortanzahl = len(keywords[0].split())
            if wortanzahl > self._config.einzeleintrag_schwellenwert:
                return ValidierungsErgebnis(
                    gueltig=False,
                    grund=(
                        f"Einzeleintrag mit {wortanzahl} Wörtern "
                        f"überschreitet Schwellenwert {self._config.einzeleintrag_schwellenwert}"
                    ),
                )

        avg = self._durchschnittliche_wortanzahl(keywords)
        if avg > self._config.wortanzahl_schwellenwert:
            return ValidierungsErgebnis(
                gueltig=False,
                grund=(
                    f"Durchschnittliche Wortanzahl {avg:.1f} "
                    f"überschreitet Schwellenwert {self._config.wortanzahl_schwellenwert}"
                ),
            )

        return ValidierungsErgebnis(gueltig=True)

    def _durchschnittliche_wortanzahl(self, keywords: list[str]) -> float:
        """Berechnet die durchschnittliche Wortanzahl über alle Einträge."""
        if not keywords:
            return 0.0
        total = sum(len(k.split()) for k in keywords)
        return total / len(keywords)

    def _enthaelt_ablehnungs_phrase(self, text: str) -> str | None:
        """Prüft case-insensitiv ob der Text eine Ablehnungsphrase enthält.

        Gibt die gefundene Phrase zurück oder None.
        """
        text_lower = text.lower()
        for phrase in self.ABLEHNUNGS_PHRASEN:
            if phrase in text_lower:
                return phrase
        return None
