"""Quick phrases (frases prontas) settings domain.

Fork FalcaoNet: user-defined snippets inserted into the WhatsApp Web
composer on demand. The application never sends a message by itself —
inserting text only fills the composer; sending stays a user action.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from zapzap.core.config.settings.base import BaseSettings

MAX_SHORTCUT_LENGTH = 32
MAX_TITLE_LENGTH = 80
MAX_TEXT_LENGTH = 4096

_SHORTCUT_PATTERN = re.compile(r"^[a-z0-9_\-]+$")


class QuickPhraseValidationError(ValueError):
    """Raised when a quick phrase does not satisfy the storage rules."""

    EMPTY_SHORTCUT = "empty_shortcut"
    INVALID_SHORTCUT = "invalid_shortcut"
    DUPLICATED_SHORTCUT = "duplicated_shortcut"
    EMPTY_TEXT = "empty_text"
    TOO_LONG = "too_long"

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class QuickPhrase:
    """One reusable snippet identified by a short shortcut."""

    shortcut: str
    title: str
    text: str

    def to_dict(self) -> dict:
        return {
            "atalho": self.shortcut,
            "titulo": self.title,
            "texto": self.text,
        }

    @classmethod
    def from_dict(cls, data) -> QuickPhrase | None:
        if not isinstance(data, dict):
            return None
        shortcut = str(data.get("atalho", "")).strip()
        text = str(data.get("texto", ""))
        if not shortcut or not text.strip():
            return None
        return cls(
            shortcut=shortcut[:MAX_SHORTCUT_LENGTH],
            title=str(data.get("titulo", "")).strip()[:MAX_TITLE_LENGTH],
            text=text[:MAX_TEXT_LENGTH],
        )


def normalize_shortcut(value: str) -> str:
    """Lower-case the shortcut and strip a leading slash and spaces."""
    value = (value or "").strip().lower()
    if value.startswith("/"):
        value = value[1:]
    return value


def validate_quick_phrase(
    shortcut: str,
    title: str,
    text: str,
    existing: list[QuickPhrase] | None = None,
    ignore_shortcut: str | None = None,
) -> QuickPhrase:
    """Validate the fields and return an immutable QuickPhrase."""
    shortcut = normalize_shortcut(shortcut)
    title = (title or "").strip()
    text = text or ""

    if not shortcut:
        raise QuickPhraseValidationError(QuickPhraseValidationError.EMPTY_SHORTCUT)
    if len(shortcut) > MAX_SHORTCUT_LENGTH or not _SHORTCUT_PATTERN.match(shortcut):
        raise QuickPhraseValidationError(QuickPhraseValidationError.INVALID_SHORTCUT)
    if not text.strip():
        raise QuickPhraseValidationError(QuickPhraseValidationError.EMPTY_TEXT)
    if len(text) > MAX_TEXT_LENGTH or len(title) > MAX_TITLE_LENGTH:
        raise QuickPhraseValidationError(QuickPhraseValidationError.TOO_LONG)
    for phrase in existing or []:
        if phrase.shortcut == shortcut and shortcut != ignore_shortcut:
            raise QuickPhraseValidationError(
                QuickPhraseValidationError.DUPLICATED_SHORTCUT
            )
    return QuickPhrase(shortcut=shortcut, title=title, text=text)


class QuickPhrasesSettings(BaseSettings):
    """Semantic access to the quick phrases list and its toggle."""

    _ENABLED = ("quick_phrases/enabled", True)
    _ITEMS = ("quick_phrases/items", "[]")

    @property
    def enabled(self) -> bool:
        return self._get_bool(self._ENABLED)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._set_bool(self._ENABLED, value)

    @property
    def items(self) -> list[QuickPhrase]:
        raw = self._get_str(self._ITEMS)
        try:
            data = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        phrases = []
        seen = set()
        for entry in data:
            phrase = QuickPhrase.from_dict(entry)
            if phrase is None or phrase.shortcut in seen:
                continue
            seen.add(phrase.shortcut)
            phrases.append(phrase)
        return phrases

    @items.setter
    def items(self, phrases: list[QuickPhrase]) -> None:
        payload = [phrase.to_dict() for phrase in phrases]
        self._set_str(self._ITEMS, json.dumps(payload, ensure_ascii=False))

    def find(self, shortcut: str) -> QuickPhrase | None:
        shortcut = normalize_shortcut(shortcut)
        for phrase in self.items:
            if phrase.shortcut == shortcut:
                return phrase
        return None

    def upsert(self, phrase: QuickPhrase, replace_shortcut: str | None = None):
        """Insert or replace a phrase, keeping the list ordered by shortcut."""
        target = replace_shortcut or phrase.shortcut
        remaining = [
            item for item in self.items
            if item.shortcut not in (target, phrase.shortcut)
        ]
        remaining.append(phrase)
        remaining.sort(key=lambda item: item.shortcut)
        self.items = remaining

    def remove(self, shortcut: str) -> None:
        shortcut = normalize_shortcut(shortcut)
        self.items = [
            item for item in self.items if item.shortcut != shortcut
        ]
