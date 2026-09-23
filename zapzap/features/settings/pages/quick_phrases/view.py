from gettext import gettext as _

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from zapzap.core.config.settings.quick_phrases import (
    MAX_SHORTCUT_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
)
from zapzap.ui.components import (
    SettingsCard,
    SettingsPage,
    SettingsSection,
    SettingsSwitchRow,
)
from zapzap.ui.primitives import Button, Label, LineEdit, TextEdit


class QuickPhrasesSettingsView(SettingsPage):
    """Composable view for quick phrases, without persistence logic."""

    def __init__(self, parent=None):
        super().__init__(
            _("Quick phrases"),
            _(
                "Reusable texts inserted into the message box on demand. "
                "Nothing is sent automatically: you always press send."
            ),
            parent,
        )
        self.setObjectName("QuickPhrasesSettingsView")
        self._setup_ui()
        self.add_stretch()

    def _setup_ui(self):
        self._add_toggle_section()
        self._add_list_section()
        self._add_editor_section()

    def _add_toggle_section(self):
        section = SettingsSection(
            _("Quick phrases"),
            _("Open the picker from the Chat menu or with Ctrl+Shift+F."),
        )
        card = SettingsCard()
        self.enabled_row = SettingsSwitchRow(
            _("Enable quick phrases"),
            _("Show the picker action in the Chat menu."),
        )
        self.enabled_row.checkbox.setAccessibleName(
            self.enabled_row.title_label.text()
        )
        self.enabled_row.title_label.setBuddy(self.enabled_row.checkbox)
        card.add_row(self.enabled_row)
        section.add_card(card)
        self.add_section(section)

    def _add_list_section(self):
        self.list_section = SettingsSection(
            _("Saved phrases"),
            _("Select a phrase to edit it, or add a new one."),
        )
        container = QWidget(self.list_section)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.phrase_list = QListWidget(container)
        self.phrase_list.setObjectName("QuickPhrasesList")
        self.phrase_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.phrase_list.setMinimumHeight(160)
        self.phrase_list.setAccessibleName(_("Saved phrases"))
        layout.addWidget(self.phrase_list)

        self.empty_label = Label(
            _("No phrases yet. Fill in the form below and save."),
            "row_description",
            container,
        )
        self.empty_label.setObjectName("QuickPhrasesEmpty")
        layout.addWidget(self.empty_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.new_button = Button(_("New phrase"), parent=container)
        self.remove_button = Button(_("Remove"), Button.DANGER, container)
        self.remove_button.setEnabled(False)
        actions.addWidget(self.new_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.list_section.add_card(container)
        self.add_section(self.list_section)

    def _add_editor_section(self):
        self.editor_section = SettingsSection(
            _("Phrase"),
            _("The shortcut is used to search in the picker (letters, numbers, - and _)."),
        )
        frame = QFrame(self.editor_section)
        frame.setObjectName("QuickPhraseEditor")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        fields = QHBoxLayout()
        fields.setSpacing(12)
        shortcut_column = QVBoxLayout()
        shortcut_column.setSpacing(4)
        self.shortcut_label = Label(_("Shortcut"), "row_title", frame)
        self.shortcut_edit = LineEdit(parent=frame)
        self.shortcut_edit.setPlaceholderText(_("Example: greeting"))
        self.shortcut_edit.setMaxLength(MAX_SHORTCUT_LENGTH)
        self.shortcut_edit.setAccessibleName(_("Shortcut"))
        self.shortcut_label.setBuddy(self.shortcut_edit)
        shortcut_column.addWidget(self.shortcut_label)
        shortcut_column.addWidget(self.shortcut_edit)

        title_column = QVBoxLayout()
        title_column.setSpacing(4)
        self.title_label_field = Label(_("Title (optional)"), "row_title", frame)
        self.title_edit = LineEdit(parent=frame)
        self.title_edit.setPlaceholderText(_("Example: Opening hours"))
        self.title_edit.setMaxLength(MAX_TITLE_LENGTH)
        self.title_edit.setAccessibleName(_("Title"))
        self.title_label_field.setBuddy(self.title_edit)
        title_column.addWidget(self.title_label_field)
        title_column.addWidget(self.title_edit)

        fields.addLayout(shortcut_column, 2)
        fields.addLayout(title_column, 3)
        layout.addLayout(fields)

        text_header = QHBoxLayout()
        self.text_label = Label(_("Text"), "row_title", frame)
        self.text_count = Label(f"0/{MAX_TEXT_LENGTH}", "row_description", frame)
        text_header.addWidget(self.text_label)
        text_header.addStretch(1)
        text_header.addWidget(self.text_count)
        layout.addLayout(text_header)

        self.text_edit = TextEdit(parent=frame)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setFixedHeight(120)
        self.text_edit.setPlaceholderText(
            _("Hello! Thanks for contacting us. How can we help?")
        )
        self.text_edit.setAccessibleName(_("Text"))
        self.text_label.setBuddy(self.text_edit)
        layout.addWidget(self.text_edit)

        self.error_label = Label("", "row_description", frame)
        self.error_label.setObjectName("QuickPhraseError")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.cancel_button = Button(_("Cancel"), parent=frame)
        self.save_button = Button(_("Save"), Button.PRIMARY, frame)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self.editor_section.add_card(frame)
        self.add_section(self.editor_section)
        frame.setStyleSheet("""
            QLabel#QuickPhraseError { color: palette(bright-text); }
        """)

    def set_dependent_enabled(self, enabled: bool):
        self.list_section.setEnabled(enabled)
        self.editor_section.setEnabled(enabled)

    def show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.setAccessibleDescription(message)
        self.error_label.show()

    def clear_error(self):
        self.error_label.hide()
        self.error_label.setText("")

    def set_editor(self, shortcut: str = "", title: str = "", text: str = ""):
        self.shortcut_edit.setText(shortcut)
        self.title_edit.setText(title)
        self.text_edit.setPlainText(text)
        self.clear_error()

    def update_empty_state(self):
        has_items = self.phrase_list.count() > 0
        self.empty_label.setVisible(not has_items)
        self.phrase_list.setVisible(has_items)

    def focus_shortcut(self):
        self.shortcut_edit.setFocus(Qt.FocusReason.OtherFocusReason)
