from gettext import gettext as _

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidgetItem

from zapzap.core.config.settings.quick_phrases import (
    MAX_TEXT_LENGTH,
    QuickPhraseValidationError,
)
from zapzap.features.settings.pages.quick_phrases.model import (
    QuickPhrasesSettingsModel,
)
from zapzap.features.settings.pages.quick_phrases.view import (
    QuickPhrasesSettingsView,
)


class QuickPhrasesSettingsController(QuickPhrasesSettingsView):
    """Controller for quick phrases persistence and signals."""

    SHORTCUT_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = QuickPhrasesSettingsModel()
        self._editing_shortcut = None
        self._initialize()

    def _initialize(self):
        self.enabled_row.checkbox.setChecked(self.model.enabled)
        self.set_dependent_enabled(self.model.enabled)
        self._reload_list()
        self._connect_signals()
        self._on_text_changed()

    def _connect_signals(self):
        self.enabled_row.checkbox.toggled.connect(self._handle_toggle_enabled)
        self.phrase_list.currentItemChanged.connect(self._on_current_changed)
        self.new_button.clicked.connect(self._start_new)
        self.remove_button.clicked.connect(self._remove_current)
        self.cancel_button.clicked.connect(self._start_new)
        self.save_button.clicked.connect(self._save)
        self.text_edit.textChanged.connect(self._on_text_changed)

    def _handle_toggle_enabled(self, is_enabled: bool):
        self.model.enabled = is_enabled
        self.set_dependent_enabled(is_enabled)

    def _reload_list(self, select_shortcut: str | None = None):
        self.phrase_list.blockSignals(True)
        self.phrase_list.clear()
        selected_item = None
        for phrase in self.model.items:
            label = f"/{phrase.shortcut}"
            if phrase.title:
                label = f"{label} — {phrase.title}"
            item = QListWidgetItem(label, self.phrase_list)
            item.setData(self.SHORTCUT_ROLE, phrase.shortcut)
            item.setToolTip(phrase.text)
            if phrase.shortcut == select_shortcut:
                selected_item = item
        self.phrase_list.blockSignals(False)
        self.update_empty_state()
        if selected_item is not None:
            self.phrase_list.setCurrentItem(selected_item)
        else:
            self.remove_button.setEnabled(False)

    def _on_current_changed(self, current, _previous):
        if current is None:
            self.remove_button.setEnabled(False)
            return
        shortcut = current.data(self.SHORTCUT_ROLE)
        phrase = next(
            (item for item in self.model.items if item.shortcut == shortcut),
            None,
        )
        if phrase is None:
            return
        self._editing_shortcut = phrase.shortcut
        self.set_editor(phrase.shortcut, phrase.title, phrase.text)
        self.remove_button.setEnabled(True)

    def _start_new(self):
        self._editing_shortcut = None
        self.phrase_list.blockSignals(True)
        self.phrase_list.setCurrentItem(None)
        self.phrase_list.blockSignals(False)
        self.remove_button.setEnabled(False)
        self.set_editor()
        self.focus_shortcut()

    def _remove_current(self):
        if self._editing_shortcut is None:
            return
        self.model.remove(self._editing_shortcut)
        self._reload_list()
        self._start_new()

    def _save(self):
        try:
            phrase = self.model.save(
                self.shortcut_edit.text(),
                self.title_edit.text(),
                self.text_edit.toPlainText(),
                replace_shortcut=self._editing_shortcut,
            )
        except QuickPhraseValidationError as error:
            self.show_error(self._error_message(error.code))
            return
        self._editing_shortcut = phrase.shortcut
        self._reload_list(select_shortcut=phrase.shortcut)
        self.clear_error()

    def _on_text_changed(self):
        count = len(self.text_edit.toPlainText())
        self.text_count.setText(f"{count}/{MAX_TEXT_LENGTH}")

    @staticmethod
    def _error_message(code: str) -> str:
        messages = {
            QuickPhraseValidationError.EMPTY_SHORTCUT: _("Enter a shortcut."),
            QuickPhraseValidationError.INVALID_SHORTCUT: _(
                "Use only letters, numbers, - and _ in the shortcut."
            ),
            QuickPhraseValidationError.DUPLICATED_SHORTCUT: _(
                "Another phrase already uses this shortcut."
            ),
            QuickPhraseValidationError.EMPTY_TEXT: _("Enter the phrase text."),
            QuickPhraseValidationError.TOO_LONG: _(
                "The phrase is too long."
            ),
        }
        return messages.get(code, _("Invalid phrase."))
