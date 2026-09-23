"""Native dialog that collects a scheduled message (number, text, date/time).

Fork FalcaoNet: the dialog only validates and returns a ``ScheduledMessage``;
persistence and sending belong to ``features.automation``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from gettext import gettext as _

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from zapzap.core.config.settings.automation import (
    MAX_SCHEDULED_TEXT_LENGTH,
    AutomationValidationError,
    ScheduledMessage,
    format_schedule_datetime,
    validate_scheduled_message,
)
from zapzap.ui.primitives import Button, CloseButton, Label, LineEdit, TextEdit


def default_schedule_time(now: datetime | None = None) -> datetime:
    """Next full hour at least 30 minutes ahead (a sane pre-filled value)."""
    now = now or datetime.now()
    candidate = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
    if candidate.minute:
        candidate = candidate.replace(minute=0) + timedelta(hours=1)
    return candidate


class ScheduleMessageDialog(QDialog):
    """Collect and validate one scheduled message without persisting it."""

    message_scheduled = pyqtSignal(object)

    DIALOG_WIDTH = 640
    DIALOG_HEIGHT = 560
    OUTER_MARGIN = 14
    WINDOW_RADIUS = 18

    def __init__(
        self,
        parent=None,
        user_id: str = "",
        account_label: str = "",
        automation_enabled: bool = True,
        now_fn=datetime.now,
    ):
        super().__init__(parent)
        self._user_id = str(user_id)
        self._account_label = account_label
        self._automation_enabled = automation_enabled
        self._now = now_fn
        self._result: ScheduledMessage | None = None

        self.setObjectName("ScheduleMessageDialog")
        self.setWindowTitle(_("Schedule message"))
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()
        self._on_text_changed()

    @property
    def scheduled_message(self) -> ScheduledMessage | None:
        return self._result

    # --- UI --------------------------------------------------------------
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(
            self.OUTER_MARGIN, self.OUTER_MARGIN,
            self.OUTER_MARGIN, self.OUTER_MARGIN,
        )
        root.setSpacing(0)

        self.window_frame = QFrame(self)
        self.window_frame.setObjectName("ScheduleMessageWindowFrame")
        root.addWidget(self.window_frame)

        shadow = QGraphicsDropShadowEffect(self.window_frame)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 75))
        self.window_frame.setGraphicsEffect(shadow)

        window_layout = QVBoxLayout(self.window_frame)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(0)

        header = QFrame(self.window_frame)
        header.setObjectName("ScheduleMessageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 18, 18, 16)
        header_layout.setSpacing(14)
        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(4)
        self.title_label = Label(_("Schedule message"), "section_title", header)
        description = _("The message is sent automatically at the chosen time.")
        if self._account_label:
            description = _("Account: {}").format(self._account_label) + "  ·  " + description
        self.description_label = Label(description, "section_description", header)
        self.description_label.setWordWrap(True)
        heading_layout.addWidget(self.title_label)
        heading_layout.addWidget(self.description_label)
        self.close_button = CloseButton(header, tooltip=_("Close"), circular=True)
        header_layout.addLayout(heading_layout, 1)
        header_layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        window_layout.addWidget(header)

        content = QWidget(self.window_frame)
        content.setObjectName("ScheduleMessageContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 12, 26, 16)
        content_layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.number_label = Label(_("Phone number (international)"), "row_title", content)
        self.number_edit = LineEdit(parent=content)
        self.number_edit.setPlaceholderText(_("Example: +55 11 99999-9999"))
        self.number_edit.setMaxLength(32)
        self.number_edit.setAccessibleName(_("Phone number"))
        self.number_label.setBuddy(self.number_edit)
        self.when_label = Label(_("Date and time"), "row_title", content)
        self.when_edit = LineEdit(parent=content)
        self.when_edit.setPlaceholderText("2026-12-31 09:00")
        self.when_edit.setText(format_schedule_datetime(default_schedule_time(self._now())))
        self.when_edit.setMaxLength(16)
        self.when_edit.setAccessibleName(_("Date and time"))
        self.when_label.setBuddy(self.when_edit)
        grid.addWidget(self.number_label, 0, 0)
        grid.addWidget(self.when_label, 0, 1)
        grid.addWidget(self.number_edit, 1, 0)
        grid.addWidget(self.when_edit, 1, 1)
        content_layout.addLayout(grid)

        self.hint_label = Label(
            _("Number with country code. Date as YYYY-MM-DD HH:MM (local time)."),
            "row_description",
            content,
        )
        self.hint_label.setWordWrap(True)
        content_layout.addWidget(self.hint_label)

        text_header = QHBoxLayout()
        self.text_label = Label(_("Message"), "row_title", content)
        self.text_count = Label(f"0/{MAX_SCHEDULED_TEXT_LENGTH}", "row_description", content)
        text_header.addWidget(self.text_label)
        text_header.addStretch(1)
        text_header.addWidget(self.text_count)
        content_layout.addLayout(text_header)

        self.text_edit = TextEdit(parent=content)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText(_("Hello! How are you?"))
        self.text_edit.setAccessibleName(_("Message"))
        self.text_edit.setAccessibleDescription(
            _("Type the message. Press Control+Enter to schedule.")
        )
        self.text_label.setBuddy(self.text_edit)
        self.text_edit.installEventFilter(self)
        content_layout.addWidget(self.text_edit, 1)

        self.error_label = Label("", "row_description", content)
        self.error_label.setObjectName("ScheduleMessageError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        content_layout.addWidget(self.error_label)

        info_box = QFrame(content)
        info_box.setObjectName("ScheduleMessageInfoBox")
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(14, 11, 14, 11)
        info_layout.setSpacing(3)
        info_title = (
            _("Automation is disabled")
            if not self._automation_enabled
            else _("Unofficial automation")
        )
        info_text = (
            _("Enable it in Settings > Automation, or the message will only wait.")
            if not self._automation_enabled
            else _("Sent over WhatsApp Web with a random delay; the number may be restricted or banned.")
        )
        self.info_title_label = Label(info_title, "row_title", info_box)
        self.info_body_label = Label(info_text, "row_description", info_box)
        self.info_body_label.setWordWrap(True)
        info_layout.addWidget(self.info_title_label)
        info_layout.addWidget(self.info_body_label)
        content_layout.addWidget(info_box)
        window_layout.addWidget(content, 1)

        footer = QFrame(self.window_frame)
        footer.setObjectName("ScheduleMessageFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 14, 22, 14)
        footer_layout.setSpacing(8)
        self.cancel_button = Button(_("Cancel"), parent=footer)
        self.schedule_button = Button(_("Schedule"), Button.PRIMARY, footer)
        self.schedule_button.setDefault(True)
        self.cancel_button.setAccessibleName(_("Cancel"))
        self.schedule_button.setAccessibleName(_("Schedule"))
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.schedule_button)
        window_layout.addWidget(footer)

    def _connect_signals(self):
        self.close_button.clicked.connect(self.reject)
        self.cancel_button.clicked.connect(self.reject)
        self.schedule_button.clicked.connect(self._submit)
        self.text_edit.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        count = len(self.text_edit.toPlainText())
        self.text_count.setText(f"{count}/{MAX_SCHEDULED_TEXT_LENGTH}")

    # --- validação ---------------------------------------------------------
    @staticmethod
    def error_message(code: str) -> str:
        messages = {
            AutomationValidationError.INVALID_NUMBER: _(
                "Enter a valid international number, with the country code."
            ),
            AutomationValidationError.EMPTY_TEXT: _("Enter the message text."),
            AutomationValidationError.TOO_LONG: _("The message is too long."),
            AutomationValidationError.INVALID_DATETIME: _(
                "Use the format YYYY-MM-DD HH:MM."
            ),
            AutomationValidationError.DATETIME_IN_PAST: _(
                "Choose a date and time in the future."
            ),
        }
        return messages.get(code, _("Invalid data."))

    def _submit(self):
        try:
            item = validate_scheduled_message(
                self._user_id,
                self.number_edit.text(),
                self.text_edit.toPlainText(),
                self.when_edit.text(),
                now=self._now(),
            )
        except AutomationValidationError as error:
            message = self.error_message(error.code)
            self.error_label.setText(message)
            self.error_label.setAccessibleDescription(message)
            self.error_label.show()
            focus = {
                AutomationValidationError.INVALID_NUMBER: self.number_edit,
                AutomationValidationError.INVALID_DATETIME: self.when_edit,
                AutomationValidationError.DATETIME_IN_PAST: self.when_edit,
            }.get(error.code, self.text_edit)
            focus.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        self.error_label.hide()
        self._result = item
        self.message_scheduled.emit(item)
        self.accept()

    # --- estilo e eventos -------------------------------------------------
    def _apply_style(self):
        self.setStyleSheet("""
            QDialog#ScheduleMessageDialog {
                background: transparent;
                color: palette(text);
            }
            QFrame#ScheduleMessageWindowFrame {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: %dpx;
            }
            QFrame#ScheduleMessageHeader,
            QFrame#ScheduleMessageFooter,
            QWidget#ScheduleMessageContent {
                background: transparent;
                border: 0;
            }
            QFrame#ScheduleMessageInfoBox {
                background: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 10px;
            }
            QLabel#ScheduleMessageError {
                color: palette(bright-text);
            }
        """ % self.WINDOW_RADIUS)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.move(parent.frameGeometry().center() - self.rect().center())
        self.number_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def eventFilter(self, watched, event):
        if watched is self.text_edit and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if (
                key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self._submit()
                key_event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)
