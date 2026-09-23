"""Resposta automática de ausência.

Fork FalcaoNet: gancho chamado a cada notificação de mensagem recebida
(``NotificationService.notify``, antes das saídas antecipadas). Decide, com
todos os freios, se enfileira uma resposta no ``AutomationRunner``; a abertura
do chat usa ``notification.click()`` (não recarrega a página).
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Callable

from zapzap.core.config.settings.automation import (
    AutomationSettings,
    is_within_daily_window,
)
from zapzap.features.automation.log import log_event
from zapzap.features.automation.runner import AutomationRunner, SendJob

KIND = "ausencia"

DECISION_OFF = "desligado"
DECISION_NO_TEXT = "sem-texto"
DECISION_OUTSIDE_SCHEDULE = "fora-do-horario"
DECISION_USER_ACTIVE = "usuario-ativo"
DECISION_NO_KEY = "sem-chave"
DECISION_COOLDOWN = "cooldown"
DECISION_ALREADY_QUEUED = "ja-na-fila"
DECISION_LIMIT = "limite-hora"
DECISION_QUEUED = "enfileirada"

_QUIET_DECISIONS = frozenset({DECISION_OFF, DECISION_USER_ACTIVE, DECISION_NO_TEXT})


def conversation_key(user_id, notification) -> str:
    """Stable per-account key: notification tag when present, else the title."""
    tag = ""
    try:
        tag = (notification.tag() or "").strip()
    except (AttributeError, RuntimeError):
        tag = ""
    if not tag:
        try:
            tag = (notification.title() or "").strip()
        except (AttributeError, RuntimeError):
            tag = ""
    if not tag:
        return ""
    return f"{user_id}|{tag}"


class AwayReplyService:
    """Decide and queue away replies; keeps cooldown persisted."""

    def __init__(
        self,
        runner: AutomationRunner,
        activity,
        limit_allows: Callable[[], bool],
        settings: AutomationSettings | None = None,
        clock: Callable[[], float] = time.time,
        now_fn: Callable[[], datetime] = datetime.now,
    ):
        self._runner = runner
        self._activity = activity
        self._limit_allows = limit_allows
        self._settings = settings or AutomationSettings()
        self._clock = clock
        self._now = now_fn
        self._in_flight: set[str] = set()

    def on_incoming(self, page, notification) -> str:
        """Evaluate one incoming notification; returns the decision code."""
        settings = self._settings
        user_id = getattr(getattr(page, "user", None), "id", "")
        title = ""
        try:
            title = (notification.title() or "").strip()
        except (AttributeError, RuntimeError):
            title = ""

        decision = self._decide(user_id, notification)
        if decision not in _QUIET_DECISIONS:
            log_event(user_id, KIND, title, decision)
        if decision != DECISION_QUEUED:
            return decision

        key = conversation_key(user_id, notification)
        text = settings.away_text
        self._in_flight.add(key)

        def _open_chat(_page_controller):
            notification.click()

        def _on_done(status: str):
            self._in_flight.discard(key)
            if status == "ok":
                cooldown = settings.load_reply_cooldown()
                cooldown.mark(key, self._clock())
                settings.save_reply_cooldown(cooldown)
            log_event(user_id, KIND, title, status, len(text))

        self._runner.enqueue(SendJob(
            kind=KIND,
            user_id=str(user_id),
            target=title,
            text=text,
            open_chat=_open_chat,
            expected_title=title or None,
            skip_groups=settings.away_skip_groups,
            close_after=True,
            on_done=_on_done,
        ))
        return decision

    def _decide(self, user_id, notification) -> str:
        settings = self._settings
        if not (settings.enabled and settings.away_enabled):
            return DECISION_OFF
        if not settings.away_text.strip():
            return DECISION_NO_TEXT
        if settings.away_schedule_enabled and not self._within_schedule():
            return DECISION_OUTSIDE_SCHEDULE
        unfocused_min = settings.away_only_when_unfocused_min
        if unfocused_min > 0 and self._activity.idle_seconds() < unfocused_min * 60:
            return DECISION_USER_ACTIVE
        key = conversation_key(user_id, notification)
        if not key:
            return DECISION_NO_KEY
        if key in self._in_flight:
            return DECISION_ALREADY_QUEUED
        cooldown = settings.load_reply_cooldown()
        cooldown_s = settings.away_cooldown_h * 3600
        now = self._clock()
        if cooldown.is_cooling(key, cooldown_s, now):
            return DECISION_COOLDOWN
        settings.save_reply_cooldown(cooldown)  # persiste a poda
        if not self._limit_allows():
            return DECISION_LIMIT
        return DECISION_QUEUED

    def _within_schedule(self) -> bool:
        settings = self._settings
        return is_within_daily_window(
            self._now(),
            settings.away_schedule_start,
            settings.away_schedule_end,
            settings.away_schedule_weekend,
        )
