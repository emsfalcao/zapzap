from gettext import gettext as _

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from zapzap.core.config.settings.automation import (
    COOLDOWN_OPTIONS_H,
    DELAY_MAX_OPTIONS_S,
    DELAY_MIN_OPTIONS_S,
    LATE_GRACE_OPTIONS_MIN,
    MAX_AWAY_TEXT_LENGTH,
    MAX_PER_HOUR_OPTIONS,
    UNFOCUSED_OPTIONS_MIN,
)
from zapzap.ui.components import (
    SettingsActionRow,
    SettingsCard,
    SettingsInfoBox,
    SettingsPage,
    SettingsSection,
    SettingsSelectRow,
    SettingsSwitchRow,
    SettingsTextRow,
)
from zapzap.ui.primitives import Button, Label, TextEdit


class AutomationSettingsView(SettingsPage):
    """Composable view for automation (away replies, scheduled messages)."""

    def __init__(self, parent=None):
        super().__init__(
            _("Automation"),
            _(
                "Automatic away replies and scheduled messages, sent over "
                "WhatsApp Web with human-like delays and hourly limits."
            ),
            parent,
        )
        self.setObjectName("AutomationSettingsView")
        self._setup_ui()
        self.add_stretch()

    def _setup_ui(self):
        self._add_warning_section()
        self._add_general_section()
        self._add_away_section()
        self._add_scheduled_section()

    # --- aviso obrigatório ----------------------------------------------------
    def _add_warning_section(self):
        section = SettingsSection(
            _("Before you enable it"),
            _("Everything here is off by default and every event is logged."),
        )
        card = SettingsCard()
        self.warning_box = SettingsInfoBox(
            _(
                "This feature acts on top of WhatsApp Web and is not official. "
                "WhatsApp may restrict or ban the number. Use it sparingly."
            ),
            "warning",
        )
        card.add_row(self.warning_box)
        section.add_card(card)
        self.add_section(section)

    # --- geral ----------------------------------------------------------------
    def _add_general_section(self):
        section = SettingsSection(
            _("General"),
            _("Limits shared by away replies and scheduled messages."),
        )
        card = SettingsCard()
        self.enabled_row = SettingsSwitchRow(
            _("Enable automation"),
            _("Master switch. Nothing runs while it is off."),
        )
        self._label_switch(self.enabled_row)
        card.add_row(self.enabled_row)

        self.delay_min_row = SettingsSelectRow(
            _("Minimum delay before sending"),
            _("Random wait, in seconds, before each automatic send."),
        )
        self._fill_combo(self.delay_min_row.combo, DELAY_MIN_OPTIONS_S, _("{} s"))
        card.add_row(self.delay_min_row)

        self.delay_max_row = SettingsSelectRow(
            _("Maximum delay before sending"),
            _("Upper bound of the random wait, in seconds."),
        )
        self._fill_combo(self.delay_max_row.combo, DELAY_MAX_OPTIONS_S, _("{} s"))
        card.add_row(self.delay_max_row)

        self.max_per_hour_row = SettingsSelectRow(
            _("Maximum automatic sends per hour"),
            _("Counts away replies and scheduled messages together."),
        )
        self._fill_combo(
            self.max_per_hour_row.combo, MAX_PER_HOUR_OPTIONS, _("{} per hour")
        )
        card.add_row(self.max_per_hour_row)

        self.log_row = SettingsActionRow(
            _("Automation log"),
            _("One line per event: account, type, target and result. No message content."),
            _("Open log"),
        )
        card.add_row(self.log_row, divider=False)
        section.add_card(card)
        self.general_section = section
        self.add_section(section)

    # --- ausência -------------------------------------------------------------
    def _add_away_section(self):
        section = SettingsSection(
            _("Away reply"),
            _("Replies once per conversation when a message arrives and you are away."),
        )
        card = SettingsCard()
        self.away_enabled_row = SettingsSwitchRow(
            _("Enable away reply"),
            _("Requires the automation master switch."),
        )
        self._label_switch(self.away_enabled_row)
        card.add_row(self.away_enabled_row)

        text_container = QWidget(card)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 8, 0, 8)
        text_layout.setSpacing(6)
        text_header = QHBoxLayout()
        self.away_text_label = Label(_("Reply text"), "row_title", text_container)
        self.away_text_count = Label(
            f"0/{MAX_AWAY_TEXT_LENGTH}", "row_description", text_container
        )
        text_header.addWidget(self.away_text_label)
        text_header.addStretch(1)
        text_header.addWidget(self.away_text_count)
        text_layout.addLayout(text_header)
        self.away_text_edit = TextEdit(parent=text_container)
        self.away_text_edit.setAcceptRichText(False)
        self.away_text_edit.setFixedHeight(96)
        self.away_text_edit.setPlaceholderText(
            _("Hi! I am away right now and will reply as soon as possible.")
        )
        self.away_text_edit.setAccessibleName(_("Reply text"))
        self.away_text_label.setBuddy(self.away_text_edit)
        text_layout.addWidget(self.away_text_edit)
        self.away_text_error = Label("", "row_description", text_container)
        self.away_text_error.setObjectName("AutomationError")
        self.away_text_error.hide()
        text_layout.addWidget(self.away_text_error)
        card.add_row(text_container)

        self.cooldown_row = SettingsSelectRow(
            _("One reply per conversation every"),
            _("The same contact does not get another automatic reply within this interval."),
        )
        self._fill_combo(self.cooldown_row.combo, COOLDOWN_OPTIONS_H, _("{} h"))
        card.add_row(self.cooldown_row)

        self.skip_groups_row = SettingsSwitchRow(
            _("Ignore groups"),
            _("Never reply automatically in group chats."),
        )
        self._label_switch(self.skip_groups_row)
        card.add_row(self.skip_groups_row)

        self.unfocused_row = SettingsSelectRow(
            _("Only when idle for"),
            _("Reply only if ZapZap had no focus or activity for this long. 0 = always."),
        )
        self._fill_combo(
            self.unfocused_row.combo, UNFOCUSED_OPTIONS_MIN, _("{} min"),
            zero_label=_("Always"),
        )
        card.add_row(self.unfocused_row)

        self.schedule_enabled_row = SettingsSwitchRow(
            _("Only within a daily window"),
            _("Restrict the away reply to the hours below."),
        )
        self._label_switch(self.schedule_enabled_row)
        card.add_row(self.schedule_enabled_row)

        self.schedule_start_row = SettingsTextRow(
            _("Window start"),
            _("HH:MM. The window may cross midnight (e.g. 18:00 to 08:00)."),
        )
        self.schedule_start_row.line_edit.setMaxLength(5)
        self.schedule_start_row.line_edit.setPlaceholderText("18:00")
        self.schedule_start_row.line_edit.setAccessibleName(_("Window start"))
        card.add_row(self.schedule_start_row)

        self.schedule_end_row = SettingsTextRow(_("Window end"), _("HH:MM."))
        self.schedule_end_row.line_edit.setMaxLength(5)
        self.schedule_end_row.line_edit.setPlaceholderText("08:00")
        self.schedule_end_row.line_edit.setAccessibleName(_("Window end"))
        card.add_row(self.schedule_end_row)

        self.schedule_error = Label("", "row_description", card)
        self.schedule_error.setObjectName("AutomationError")
        self.schedule_error.hide()
        card.add_row(self.schedule_error, divider=False)

        self.schedule_weekend_row = SettingsSwitchRow(
            _("Whole weekend"),
            _("Also reply all day on Saturdays and Sundays."),
        )
        self._label_switch(self.schedule_weekend_row)
        card.add_row(self.schedule_weekend_row, divider=False)

        section.add_card(card)
        self.away_section = section
        self.add_section(section)

    # --- agendadas ------------------------------------------------------------
    def _add_scheduled_section(self):
        section = SettingsSection(
            _("Scheduled messages"),
            _("Create them from the Chat menu (Schedule message…, Ctrl+Shift+A)."),
        )
        card = SettingsCard()
        self.scheduled_enabled_row = SettingsSwitchRow(
            _("Enable scheduled messages"),
            _("Requires the automation master switch."),
        )
        self._label_switch(self.scheduled_enabled_row)
        card.add_row(self.scheduled_enabled_row)

        self.grace_row = SettingsSelectRow(
            _("Late tolerance"),
            _("If ZapZap was closed at the time, still send when the delay is below this; otherwise mark it expired."),
        )
        self._fill_combo(
            self.grace_row.combo, LATE_GRACE_OPTIONS_MIN, _("{} min")
        )
        card.add_row(self.grace_row)

        list_container = QWidget(card)
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 8, 0, 8)
        list_layout.setSpacing(8)
        self.scheduled_list = QListWidget(list_container)
        self.scheduled_list.setObjectName("AutomationScheduledList")
        self.scheduled_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.scheduled_list.setMinimumHeight(140)
        self.scheduled_list.setAccessibleName(_("Scheduled messages"))
        list_layout.addWidget(self.scheduled_list)
        self.scheduled_empty_label = Label(
            _("No scheduled messages."), "row_description", list_container
        )
        list_layout.addWidget(self.scheduled_empty_label)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.resend_button = Button(_("Resend now"), parent=list_container)
        self.remove_scheduled_button = Button(_("Remove"), Button.DANGER, list_container)
        self.resend_button.setEnabled(False)
        self.remove_scheduled_button.setEnabled(False)
        actions.addWidget(self.resend_button)
        actions.addWidget(self.remove_scheduled_button)
        actions.addStretch(1)
        list_layout.addLayout(actions)
        card.add_row(list_container, divider=False)

        section.add_card(card)
        self.scheduled_section = section
        self.add_section(section)
        self.setStyleSheet(
            self.styleSheet()
            + "\nQLabel#AutomationError { color: palette(bright-text); }"
        )

    # --- utilitários ---------------------------------------------------------
    @staticmethod
    def _label_switch(row):
        row.checkbox.setAccessibleName(row.title_label.text())
        row.title_label.setBuddy(row.checkbox)

    @staticmethod
    def _fill_combo(combo, values, template, zero_label=None):
        for value in values:
            label = zero_label if (value == 0 and zero_label) else template.format(value)
            combo.addItem(label, value)

    @staticmethod
    def select_combo_value(combo, value):
        index = combo.findData(value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)

    def set_dependent_enabled(self, enabled: bool):
        self.away_section.setEnabled(enabled)
        self.scheduled_section.setEnabled(enabled)

    def show_schedule_error(self, message: str):
        self.schedule_error.setText(message)
        self.schedule_error.setAccessibleDescription(message)
        self.schedule_error.show()

    def clear_schedule_error(self):
        self.schedule_error.hide()
        self.schedule_error.setText("")

    def update_scheduled_empty_state(self):
        has_items = self.scheduled_list.count() > 0
        self.scheduled_empty_label.setVisible(not has_items)
        self.scheduled_list.setVisible(has_items)
