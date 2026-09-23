"""Envio de mensagens agendadas.

Fork FalcaoNet: ``QTimer`` a cada 30 s pega os itens pendentes vencidos
(respeitando a tolerância de atraso), enfileira um por vez no
``AutomationRunner`` e atualiza o status persistido. O chat abre por deeplink
``web.whatsapp.com/send?phone=`` SEM ``text`` (via ``xdg_open_chat``, sem
recarregar a página); o texto entra pelo ``insert_text_in_composer``.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Callable

from PyQt6.QtCore import QObject, QTimer

from zapzap.core.config.settings.automation import (
    MAX_SCHEDULED_ATTEMPTS,
    RETRY_WAIT_S,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    AutomationSettings,
    AutomationValidationError,
    ScheduledMessage,
    due_scheduled_items,
    split_e164,
)
from zapzap.features.automation.log import log_event
from zapzap.features.automation.runner import AutomationRunner, SendJob
from zapzap.features.browser.web.open_chat import ChatTarget, build_open_chat_url

logger = logging.getLogger(__name__)

KIND = "agendada"
TICK_MS = 30_000
RESULT_EXPIRED = "expirada"
RESULT_LIMIT = "limite-hora"


class ScheduledSendService(QObject):
    """Periodic scheduler for :class:`ScheduledMessage` items."""

    def __init__(
        self,
        runner: AutomationRunner,
        settings: AutomationSettings | None = None,
        parent: QObject | None = None,
        now_fn: Callable[[], datetime] = datetime.now,
        tick_ms: int = TICK_MS,
    ):
        super().__init__(parent)
        self._runner = runner
        self._settings = settings or AutomationSettings()
        self._now = now_fn
        self._in_flight: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.tick)

    # --- ciclo de vida -------------------------------------------------
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # --- API -----------------------------------------------------------
    def resend_now(self, item_id: str) -> ScheduledMessage | None:
        """Re-arm a failed/expired item for the next tick."""
        item = self._settings.find_scheduled(item_id)
        if item is None:
            return None
        updated = self._settings.update_scheduled(
            item_id,
            status=STATUS_PENDING,
            attempts=0,
            last_error="",
            last_attempt=None,
            when=self._now(),
        )
        log_event(item.user_id, KIND, item.number, "reenvio-solicitado")
        QTimer.singleShot(0, self.tick)
        return updated

    def tick(self) -> list[str]:
        """Expire late items and enqueue at most one due item. Returns ids queued."""
        settings = self._settings
        if not (settings.enabled and settings.scheduled_enabled):
            return []
        now = self._now()
        to_send, to_expire = due_scheduled_items(
            settings.scheduled_items,
            now,
            settings.scheduled_late_grace_min,
            RETRY_WAIT_S,
        )
        for item in to_expire:
            settings.update_scheduled(
                item.id, status=STATUS_EXPIRED, last_error=RESULT_EXPIRED
            )
            log_event(item.user_id, KIND, item.number, RESULT_EXPIRED, len(item.text))

        # Um item por tick e nunca dois em voo: os envios já são serializados
        # pelo runner, com atraso humano entre eles.
        if self._in_flight or not to_send:
            return []
        item = to_send[0]
        self._enqueue(item)
        return [item.id] if item.id in self._in_flight else []

    # --- interno ---------------------------------------------------------
    def _enqueue(self, item: ScheduledMessage) -> None:
        try:
            calling_code, national = split_e164(item.number)
        except AutomationValidationError:
            self._settings.update_scheduled(
                item.id, status=STATUS_FAILED, last_error="numero-invalido"
            )
            log_event(item.user_id, KIND, item.number, "numero-invalido")
            return
        url = build_open_chat_url(ChatTarget(calling_code, national))
        self._in_flight.add(item.id)

        def _open_chat(page_controller):
            page_controller.xdg_open_chat(url)

        self._runner.enqueue(SendJob(
            kind=KIND,
            user_id=item.user_id,
            target=item.number,
            text=item.text,
            open_chat=_open_chat,
            expected_digits=item.number,
            on_done=lambda status: self._on_done(item.id, status),
        ))

    def _on_done(self, item_id: str, status: str) -> None:
        self._in_flight.discard(item_id)
        settings = self._settings
        item = settings.find_scheduled(item_id)
        if item is None:
            return
        now = self._now()
        if status == "ok":
            settings.update_scheduled(
                item_id, status=STATUS_SENT, last_error="", last_attempt=now
            )
        elif status == RESULT_LIMIT:
            # Sem cota nesta hora: não conta tentativa, só espera o retry.
            settings.update_scheduled(
                item_id, last_error=status, last_attempt=now
            )
        else:
            attempts = item.attempts + 1
            new_status = (
                STATUS_FAILED if attempts >= MAX_SCHEDULED_ATTEMPTS
                else STATUS_PENDING
            )
            settings.update_scheduled(
                item_id,
                status=new_status,
                attempts=attempts,
                last_error=status,
                last_attempt=now,
            )
        log_event(item.user_id, KIND, item.number, status, len(item.text))
