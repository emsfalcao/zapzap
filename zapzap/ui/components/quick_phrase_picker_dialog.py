"""Native picker that returns a quick phrase to insert in the composer.

Fork FalcaoNet: the dialog only chooses text. Sending is never triggered.
"""

from __future__ import annotations

from gettext import gettext as _

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zapzap.core.config.settings.quick_phrases import (
    QuickPhrase,
    QuickPhrasesSettings,
)
from zapzap.ui.primitives import Button, CloseButton, Label, LineEdit, TextEdit


class QuickPhrasePickerDialog(QDialog):
    """Search and choose a saved phrase; emits the text on accept."""

    phrase_chosen = pyqtSignal(str)

    DIALOG_WIDTH = 620
    DIALOG_HEIGHT = 520
    OUTER_MARGIN = 14
    WINDOW_RADIUS = 18
    SHORTCUT_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None, phrases: list[QuickPhrase] | None = None):
        super().__init__(parent)
        self._phrases = (
            list(phrases) if phrases is not None
            else QuickPhrasesSettings().items
        )
        self._chosen_text = None

        self.setObjectName("QuickPhrasePickerDialog")
        self.setWindowTitle(_("Quick phrases"))
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)

        self._setup_ui()
        self._populate(self._phrases)
        self._connect_signals()
        self._apply_style()
        self._refresh_state()

    @property
    def chosen_text(self) -> str | None:
        return self._chosen_text

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(
            self.OUTER_MARGIN,
            self.OUTER_MARGIN,
            self.OUTER_MARGIN,
            self.OUTER_MARGIN,
        )
        root.setSpacing(0)

        self.window_frame = QFrame(self)
        self.window_frame.setObjectName("QuickPhraseWindowFrame")
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
        header.setObjectName("QuickPhraseHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 18, 18, 16)
        header_layout.setSpacing(14)
        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(4)
        self.title_label = Label(_("Quick phrases"), "section_title", header)
        self.description_label = Label(
            _("Choose a phrase to insert in the message box. You still press send."),
            "section_description",
            header,
        )
        heading_layout.addWidget(self.title_label)
        heading_layout.addWidget(self.description_label)
        self.close_button = CloseButton(header, tooltip=_("Close"), circular=True)
        header_layout.addLayout(heading_layout, 1)
        header_layout.addWidget(
            self.close_button, alignment=Qt.AlignmentFlag.AlignTop
        )
        window_layout.addWidget(header)

        content = QWidget(self.window_frame)
        content.setObjectName("QuickPhraseContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 12, 26, 16)
        content_layout.setSpacing(8)

        self.search_edit = LineEdit(parent=content)
        self.search_edit.setPlaceholderText(_("Search by shortcut, title or text"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName(_("Search phrases"))
        content_layout.addWidget(self.search_edit)

        self.phrase_list = QListWidget(content)
        self.phrase_list.setObjectName("QuickPhraseList")
        self.phrase_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.phrase_list.setAccessibleName(_("Saved phrases"))
        content_layout.addWidget(self.phrase_list, 1)

        self.empty_label = Label(
            _("No phrases saved. Add some in Settings > Quick phrases."),
            "row_description",
            content,
        )
        self.empty_label.setObjectName("QuickPhraseEmpty")
        self.empty_label.setWordWrap(True)
        content_layout.addWidget(self.empty_label)

        self.preview = TextEdit(parent=content)
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(96)
        self.preview.setAccessibleName(_("Phrase preview"))
        content_layout.addWidget(self.preview)
        window_layout.addWidget(content, 1)

        footer = QFrame(self.window_frame)
        footer.setObjectName("QuickPhraseFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 14, 22, 14)
        footer_layout.setSpacing(8)
        self.cancel_button = Button(_("Cancel"), parent=footer)
        self.insert_button = Button(_("Insert"), Button.PRIMARY, footer)
        self.insert_button.setDefault(True)
        self.cancel_button.setAccessibleName(_("Cancel"))
        self.insert_button.setAccessibleName(_("Insert"))
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.insert_button)
        window_layout.addWidget(footer)

    def _populate(self, phrases: list[QuickPhrase]):
        self.phrase_list.clear()
        for phrase in phrases:
            label = f"/{phrase.shortcut}"
            if phrase.title:
                label = f"{label} — {phrase.title}"
            item = QListWidgetItem(label, self.phrase_list)
            item.setData(self.SHORTCUT_ROLE, phrase.shortcut)
            item.setData(Qt.ItemDataRole.UserRole, phrase.text)
        if self.phrase_list.count():
            self.phrase_list.setCurrentRow(0)

    def _connect_signals(self):
        self.close_button.clicked.connect(self.reject)
        self.cancel_button.clicked.connect(self.reject)
        self.insert_button.clicked.connect(self._submit)
        self.search_edit.textChanged.connect(self._filter)
        self.search_edit.returnPressed.connect(self._submit)
        self.phrase_list.currentItemChanged.connect(
            lambda *_args: self._refresh_state()
        )
        self.phrase_list.itemActivated.connect(lambda _item: self._submit())

    def _filter(self, text: str):
        needle = (text or "").strip().lower()
        if needle.startswith("/"):
            needle = needle[1:]
        if not needle:
            self._populate(self._phrases)
        else:
            matches = [
                phrase for phrase in self._phrases
                if needle in phrase.shortcut.lower()
                or needle in phrase.title.lower()
                or needle in phrase.text.lower()
            ]
            self._populate(matches)
        self._refresh_state()

    def _current_text(self) -> str | None:
        item = self.phrase_list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _refresh_state(self):
        has_any = bool(self._phrases)
        self.empty_label.setVisible(not has_any)
        text = self._current_text()
        self.preview.setPlainText(text or "")
        self.insert_button.setEnabled(bool(text))

    def _submit(self):
        text = self._current_text()
        if not text:
            return
        self._chosen_text = text
        self.phrase_chosen.emit(text)
        self.accept()

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog#QuickPhrasePickerDialog {
                background: transparent;
                color: palette(text);
            }
            QFrame#QuickPhraseWindowFrame {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: %dpx;
            }
            QFrame#QuickPhraseHeader,
            QFrame#QuickPhraseFooter,
            QWidget#QuickPhraseContent {
                background: transparent;
                border: 0;
            }
            QListWidget#QuickPhraseList {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 10px;
                padding: 4px;
            }
            QListWidget#QuickPhraseList::item {
                padding: 6px 8px;
                border-radius: 6px;
            }
            QListWidget#QuickPhraseList::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """ % self.WINDOW_RADIUS)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.move(
                parent.frameGeometry().center() - self.rect().center()
            )
        self.search_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.search_edit.hasFocus():
            row = self.phrase_list.currentRow()
            step = 1 if key == Qt.Key.Key_Down else -1
            new_row = max(0, min(self.phrase_list.count() - 1, row + step))
            self.phrase_list.setCurrentRow(new_row)
            event.accept()
            return
        super().keyPressEvent(event)
