"""Executor único e serializado dos envios automáticos.

Fork FalcaoNet: uma fila, um envio por vez (ausência e agendadas compartilham
o mesmo runner). Cada trabalho passa por:

    atraso humano → conta ativa? → logado? → abrir chat → poll até o chat certo
    → grupo? → inserir texto (``insert_text_in_composer``) → clicar em enviar
    → (opcional) fechar conversa → ``on_done(status)``

Tudo assíncrono com ``QTimer.singleShot``; nunca ``sleep``. Os seletores e o
JavaScript vêm de :mod:`zapzap.features.automation.dom`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import random
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer

from zapzap.features.automation import dom
from zapzap.features.browser.web.open_chat import normalize_phone_digits

logger = logging.getLogger(__name__)

STATUS_ACCOUNT_INACTIVE = "conta-inativa"
STATUS_PAGE_UNAVAILABLE = "pagina-indisponivel"
STATUS_OPEN_CHAT_ERROR = "erro-abrir-chat"
STATUS_GROUP_SKIPPED = "grupo-ignorado"
STATUS_LIMIT = "limite-hora"

DEFAULT_STEP_DELAY_MS = (300, 900)
DEFAULT_POLL_INTERVAL_MS = 500
DEFAULT_POLL_TIMEOUT_MS = 10_000
DEFAULT_GAP_BETWEEN_JOBS_MS = 2_000


@dataclass
class SendJob:
    """One automatic send. ``open_chat`` receives the PageController."""

    kind: str
    user_id: str
    target: str
    text: str
    open_chat: Callable[[Any], None]
    expected_title: str | None = None
    expected_digits: str | None = None
    skip_groups: bool = False
    close_after: bool = False
    on_done: Callable[[str], None] | None = None


class AutomationRunner(QObject):
    """Serialized state machine that performs the DOM steps of one send."""

    def __init__(
        self,
        webview_provider: Callable[[str], Any],
        delay_range_provider: Callable[[], tuple[float, float]],
        limit_gate: Callable[[], bool] | None = None,
        parent: QObject | None = None,
        step_delay_ms: tuple[int, int] = DEFAULT_STEP_DELAY_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        poll_timeout_ms: int = DEFAULT_POLL_TIMEOUT_MS,
        gap_between_jobs_ms: int = DEFAULT_GAP_BETWEEN_JOBS_MS,
        random_fn: Callable[[float, float], float] = random.uniform,
    ):
        super().__init__(parent)
        self._webview_provider = webview_provider
        self._delay_range_provider = delay_range_provider
        self._limit_gate = limit_gate or (lambda: True)
        self._step_delay_ms = step_delay_ms
        self._poll_interval_ms = poll_interval_ms
        self._poll_timeout_ms = poll_timeout_ms
        self._gap_between_jobs_ms = gap_between_jobs_ms
        self._random = random_fn
        self._queue: deque[SendJob] = deque()
        self._current: SendJob | None = None
        self._generation = 0
        self._stopped = False

    # --- API ------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self._current is not None

    @property
    def pending(self) -> int:
        return len(self._queue) + (1 if self._current else 0)

    def enqueue(self, job: SendJob) -> None:
        self._queue.append(job)
        if self._current is None:
            QTimer.singleShot(0, self._start_next)

    def stop(self) -> None:
        """Drop the queue and ignore callbacks of the job in flight."""
        self._stopped = True
        self._generation += 1
        self._queue.clear()
        self._current = None

    # --- máquina de estados --------------------------------------------
    def _start_next(self) -> None:
        if self._stopped or self._current is not None or not self._queue:
            return
        self._current = self._queue.popleft()
        self._generation += 1
        generation = self._generation
        low, high = self._delay_range_provider()
        low = max(0.0, float(low))
        high = max(low, float(high))
        delay_ms = int(self._random(low, high) * 1000)
        QTimer.singleShot(delay_ms, lambda: self._resolve_page(generation))

    def _alive(self, generation: int) -> bool:
        return not self._stopped and generation == self._generation and self._current is not None

    def _later(self, generation: int, callback: Callable[[], None]) -> None:
        low, high = self._step_delay_ms
        delay = int(self._random(low, high)) if high > low else int(low)
        QTimer.singleShot(delay, lambda: self._alive(generation) and callback())

    def _run_js(self, generation: int, page, script: str, callback) -> None:
        def _guarded(result):
            if self._alive(generation):
                callback(result)

        try:
            page.runJavaScript(script, _guarded)
        except RuntimeError:
            self._finish(generation, STATUS_PAGE_UNAVAILABLE)

    def _resolve_page(self, generation: int) -> None:
        if not self._alive(generation):
            return
        job = self._current
        try:
            webview = self._webview_provider(job.user_id)
            page = webview.page() if webview is not None else None
        except RuntimeError:
            page = None
        if page is None:
            self._finish(generation, STATUS_ACCOUNT_INACTIVE)
            return

        def _on_state(result):
            state = dom.parse_chat_state(result)
            if state["status"] == dom.STATUS_NOT_LOGGED:
                self._finish(generation, dom.STATUS_NOT_LOGGED)
                return
            self._open_chat(generation, page, state["header"])

        self._run_js(generation, page, dom.build_chat_state_script(), _on_state)

    def _open_chat(self, generation: int, page, header_before: str) -> None:
        job = self._current
        try:
            job.open_chat(page)
        except Exception:
            logger.warning("Automation could not open the chat", exc_info=True)
            self._finish(generation, STATUS_OPEN_CHAT_ERROR)
            return
        polls = max(1, self._poll_timeout_ms // max(1, self._poll_interval_ms))
        self._later(
            generation,
            lambda: self._poll_chat(generation, page, header_before, polls),
        )

    def _chat_is_ready(self, job: SendJob, state: dict, header_before: str) -> bool:
        if state["status"] != dom.STATUS_OK:
            return False
        header = state["header"].strip()
        if job.expected_title:
            return header == job.expected_title.strip()
        if job.expected_digits:
            digits = normalize_phone_digits(header)
            if digits and digits == job.expected_digits:
                return True
            return bool(header) and header != header_before.strip()
        return True

    def _poll_chat(self, generation: int, page, header_before: str, remaining: int) -> None:
        job = self._current

        def _on_state(result):
            state = dom.parse_chat_state(result)
            if state["dialog"] == dom.STATUS_INVALID_NUMBER:
                self._finish(generation, dom.STATUS_INVALID_NUMBER)
                return
            if state["status"] == dom.STATUS_NOT_LOGGED:
                self._finish(generation, dom.STATUS_NOT_LOGGED)
                return
            if self._chat_is_ready(job, state, header_before):
                self._check_group(generation, page)
                return
            if remaining <= 1:
                self._finish(generation, dom.STATUS_CHAT_NOT_OPENED)
                return
            QTimer.singleShot(
                self._poll_interval_ms,
                lambda: self._alive(generation)
                and self._poll_chat(generation, page, header_before, remaining - 1),
            )

        self._run_js(generation, page, dom.build_chat_state_script(), _on_state)

    def _check_group(self, generation: int, page) -> None:
        job = self._current
        if not job.skip_groups:
            self._later(generation, lambda: self._insert_text(generation, page))
            return

        def _on_group(result):
            if result == dom.STATUS_GROUP:
                self._finish(generation, STATUS_GROUP_SKIPPED)
                return
            self._later(generation, lambda: self._insert_text(generation, page))

        self._run_js(generation, page, dom.build_is_group_script(), _on_group)

    def _insert_text(self, generation: int, page) -> None:
        job = self._current

        def _on_inserted(result):
            if not self._alive(generation):
                return
            if result == dom.STATUS_NO_COMPOSER:
                self._finish(generation, dom.STATUS_NO_COMPOSER)
                return
            self._later(generation, lambda: self._click_send(generation, page))

        try:
            page.insert_text_in_composer(job.text, _on_inserted)
        except RuntimeError:
            self._finish(generation, STATUS_PAGE_UNAVAILABLE)

    def _click_send(self, generation: int, page) -> None:
        # Freio global (limite por hora) avaliado no último instante, já com
        # o texto no compositor: sem cota, o texto fica como rascunho.
        if not self._limit_gate():
            self._finish(generation, STATUS_LIMIT)
            return

        def _on_click(result):
            status = result if isinstance(result, str) and result else dom.STATUS_NO_SEND_BUTTON
            job = self._current
            if status == dom.STATUS_OK and job is not None and job.close_after:
                # Fora da geração: o trabalho já termina aqui, e o Escape só
                # devolve a tela ao estado anterior (melhor esforço).
                QTimer.singleShot(
                    int(self._step_delay_ms[1]),
                    lambda: self._close_conversation(page),
                )
            self._finish(generation, status)

        self._run_js(generation, page, dom.build_click_send_script(), _on_click)

    @staticmethod
    def _close_conversation(page) -> None:
        try:
            page.close_conversation()
        except RuntimeError:
            pass

    def _finish(self, generation: int, status: str) -> None:
        if not self._alive(generation):
            return
        job = self._current
        self._current = None
        self._generation += 1
        if job.on_done is not None:
            try:
                job.on_done(status)
            except Exception:
                logger.warning("Automation on_done failed", exc_info=True)
        if self._queue and not self._stopped:
            QTimer.singleShot(self._gap_between_jobs_ms, self._start_next)
