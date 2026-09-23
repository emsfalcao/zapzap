"""Monitor de atividade do usuário (foco da janela, teclado e mouse).

Fork FalcaoNet: a resposta de ausência só dispara quando o usuário não usou o
aplicativo nos últimos N minutos. O monitor vive pendurado no ``QApplication``
(sobrevive ao ``restartInterface``) e guarda um relógio monotônico.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication

_ACTIVITY_EVENTS = frozenset({
    QEvent.Type.KeyPress,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
    QEvent.Type.WindowActivate,
    QEvent.Type.FocusIn,
})


class ActivityMonitor(QObject):
    """Track the last time the person interacted with any ZapZap window."""

    def __init__(self, app: QApplication | None = None, clock=None):
        super().__init__(app)
        self._clock = clock or time.monotonic
        self._last_activity = self._clock()
        self._app = app
        if app is not None:
            app.installEventFilter(self)
            app.focusWindowChanged.connect(self._on_focus_window_changed)
            app.applicationStateChanged.connect(self._on_state_changed)

    # --- consulta --------------------------------------------------------
    @property
    def last_activity(self) -> float:
        return self._last_activity

    def touch(self) -> None:
        self._last_activity = self._clock()

    def is_application_active(self) -> bool:
        if self._app is None:
            return False
        try:
            return (
                self._app.applicationState()
                == Qt.ApplicationState.ApplicationActive
            )
        except RuntimeError:
            return False

    def idle_seconds(self) -> float:
        """Seconds since the last interaction; 0 while a window has focus."""
        if self.is_application_active():
            return 0.0
        return max(0.0, self._clock() - self._last_activity)

    # --- ganchos ---------------------------------------------------------
    def eventFilter(self, watched, event):
        try:
            if event.type() in _ACTIVITY_EVENTS:
                self.touch()
        except RuntimeError:
            pass
        return False

    def _on_focus_window_changed(self, window):
        if window is not None:
            self.touch()

    def _on_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationActive:
            self.touch()
