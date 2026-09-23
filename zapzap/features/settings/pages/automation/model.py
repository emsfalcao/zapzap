from __future__ import annotations

from zapzap.core.config.settings.automation import (
    AutomationSettings,
    ScheduledMessage,
    parse_time_hhmm,
    validate_away_text,
)


class AutomationSettingsModel:
    """Model for the automation page: thin façade over AutomationSettings."""

    def __init__(self) -> None:
        self._settings = AutomationSettings()

    @property
    def settings(self) -> AutomationSettings:
        return self._settings

    def save_away_text(self, text: str) -> str:
        """Validate and persist; raises AutomationValidationError."""
        text = validate_away_text(text)
        self._settings.away_text = text
        return text

    def save_schedule_window(self, start: str, end: str) -> None:
        """Validate both HH:MM values before persisting either."""
        parse_time_hhmm(start)
        parse_time_hhmm(end)
        self._settings.away_schedule_start = start
        self._settings.away_schedule_end = end

    @property
    def scheduled_items(self) -> list[ScheduledMessage]:
        return self._settings.scheduled_items

    def remove_scheduled(self, item_id: str) -> None:
        self._settings.remove_scheduled(item_id)
