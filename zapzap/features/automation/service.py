"""Fachada da automação, pendurada no ``QApplication``.

Fork FalcaoNet: compõe o monitor de atividade, o runner único, o limite por
hora (compartilhado entre ausência e agendadas), a resposta de ausência e o
agendador. Sobrevive ao ``restartInterface`` porque localiza a janela e o
navegador dinamicamente por ``app.getWindow()``.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PyQt6.QtCore import QObject

from zapzap.core.config.settings.automation import AutomationSettings, HourlyLimit
from zapzap.features.automation.activity import ActivityMonitor
from zapzap.features.automation.away_reply import AwayReplyService
from zapzap.features.automation.runner import AutomationRunner
from zapzap.features.automation.scheduler import ScheduledSendService

logger = logging.getLogger(__name__)


class AutomationService(QObject):
    """Single owner of the automation runtime; ``instance()`` may be None."""

    _instance: AutomationService | None = None

    def __init__(
        self,
        app,
        window_provider: Callable[[], object] | None = None,
        settings: AutomationSettings | None = None,
        clock: Callable[[], float] = time.time,
    ):
        super().__init__(app)
        self._app = app
        self._window_provider = window_provider or (lambda: app.getWindow())
        self._settings = settings or AutomationSettings()
        self._clock = clock
        self._limit = self._settings.load_hourly_limit()
        self.activity = ActivityMonitor(app)
        self.runner = AutomationRunner(
            webview_provider=self._webview_for_user,
            delay_range_provider=self._delay_range,
            limit_gate=self._consume_quota,
            parent=self,
        )
        self.away = AwayReplyService(
            self.runner,
            self.activity,
            limit_allows=self._limit_allows,
            settings=self._settings,
            clock=clock,
        )
        self.scheduler = ScheduledSendService(
            self.runner, settings=self._settings, parent=self
        )
        AutomationService._instance = self

    # --- ciclo de vida -------------------------------------------------
    @classmethod
    def instance(cls) -> AutomationService | None:
        return cls._instance

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.runner.stop()
        self._settings.save_hourly_limit(self._limit)
        if AutomationService._instance is self:
            AutomationService._instance = None

    # --- gancho de notificação ------------------------------------------
    @classmethod
    def notify_incoming(cls, page, notification) -> str | None:
        """Called by NotificationService for every incoming notification."""
        service = cls._instance
        if service is None:
            return None
        try:
            return service.away.on_incoming(page, notification)
        except Exception:
            logger.warning("Away reply hook failed", exc_info=True)
            return None

    # --- limite por hora --------------------------------------------------
    def _limit_allows(self) -> bool:
        return self._limit.allows(self._settings.max_per_hour, self._clock())

    def _consume_quota(self) -> bool:
        now = self._clock()
        if not self._limit.allows(self._settings.max_per_hour, now):
            return False
        self._limit.record(now)
        self._settings.save_hourly_limit(self._limit)
        return True

    def sends_last_hour(self) -> int:
        return self._limit.count(self._clock())

    # --- localização dinâmica --------------------------------------------
    def _delay_range(self) -> tuple[float, float]:
        return (
            float(self._settings.delay_min_s),
            float(self._settings.delay_max_s),
        )

    def _webview_for_user(self, user_id):
        try:
            window = self._window_provider()
        except Exception:
            return None
        browser = getattr(window, "browser", None)
        if browser is None:
            return None
        lookup = getattr(browser, "webview_for_user_id", None)
        if lookup is None:
            return None
        try:
            return lookup(user_id)
        except RuntimeError:
            return None
