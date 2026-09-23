from __future__ import annotations

from zapzap.core.config.settings.quick_phrases import (
    QuickPhrase,
    QuickPhrasesSettings,
    validate_quick_phrase,
)


class QuickPhrasesSettingsModel:
    """Model for quick phrases persistence."""

    def __init__(self) -> None:
        self._settings = QuickPhrasesSettings()

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._settings.enabled = value

    @property
    def items(self) -> list[QuickPhrase]:
        return self._settings.items

    def save(
        self,
        shortcut: str,
        title: str,
        text: str,
        replace_shortcut: str | None = None,
    ) -> QuickPhrase:
        """Validate and persist a phrase; raises QuickPhraseValidationError."""
        phrase = validate_quick_phrase(
            shortcut,
            title,
            text,
            existing=self._settings.items,
            ignore_shortcut=replace_shortcut,
        )
        self._settings.upsert(phrase, replace_shortcut=replace_shortcut)
        return phrase

    def remove(self, shortcut: str) -> None:
        self._settings.remove(shortcut)
