from gettext import gettext as _

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QListWidgetItem

from zapzap.core.config.settings.automation import (
    MAX_AWAY_TEXT_LENGTH,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    AutomationValidationError,
    format_schedule_datetime,
)
from zapzap.features.automation.log import automation_logger, log_path
from zapzap.features.automation.service import AutomationService
from zapzap.features.settings.pages.automation.model import (
    AutomationSettingsModel,
)
from zapzap.features.settings.pages.automation.view import (
    AutomationSettingsView,
)


class AutomationSettingsController(AutomationSettingsView):
    """Controller for automation persistence and the scheduled list."""

    ITEM_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = AutomationSettingsModel()
        self._initialize()

    # --- carga ---------------------------------------------------------------
    def _initialize(self):
        settings = self.model.settings
        self.enabled_row.checkbox.setChecked(settings.enabled)
        self.select_combo_value(self.delay_min_row.combo, settings.delay_min_s)
        self.select_combo_value(self.delay_max_row.combo, settings.delay_max_s)
        self.select_combo_value(self.max_per_hour_row.combo, settings.max_per_hour)

        self.away_enabled_row.checkbox.setChecked(settings.away_enabled)
        self.away_text_edit.setPlainText(settings.away_text)
        self.select_combo_value(self.cooldown_row.combo, settings.away_cooldown_h)
        self.skip_groups_row.checkbox.setChecked(settings.away_skip_groups)
        self.select_combo_value(
            self.unfocused_row.combo, settings.away_only_when_unfocused_min
        )
        self.schedule_enabled_row.checkbox.setChecked(settings.away_schedule_enabled)
        self.schedule_start_row.line_edit.setText(settings.away_schedule_start)
        self.schedule_end_row.line_edit.setText(settings.away_schedule_end)
        self.schedule_weekend_row.checkbox.setChecked(settings.away_schedule_weekend)

        self.scheduled_enabled_row.checkbox.setChecked(settings.scheduled_enabled)
        self.select_combo_value(self.grace_row.combo, settings.scheduled_late_grace_min)

        self.set_dependent_enabled(settings.enabled)
        self._set_schedule_rows_enabled(settings.away_schedule_enabled)
        self._on_away_text_changed()
        self.reload_scheduled_list()
        self._connect_signals()

    def _connect_signals(self):
        self.enabled_row.checkbox.toggled.connect(self._on_enabled)
        self.delay_min_row.combo.currentIndexChanged.connect(self._on_delay_changed)
        self.delay_max_row.combo.currentIndexChanged.connect(self._on_delay_changed)
        self.max_per_hour_row.combo.currentIndexChanged.connect(
            lambda _index: self._set("max_per_hour", self.max_per_hour_row.combo.currentData())
        )
        self.log_row.button.clicked.connect(self._open_log)

        self.away_enabled_row.checkbox.toggled.connect(
            lambda value: self._set("away_enabled", value)
        )
        self.away_text_edit.textChanged.connect(self._on_away_text_changed)
        self.cooldown_row.combo.currentIndexChanged.connect(
            lambda _index: self._set("away_cooldown_h", self.cooldown_row.combo.currentData())
        )
        self.skip_groups_row.checkbox.toggled.connect(
            lambda value: self._set("away_skip_groups", value)
        )
        self.unfocused_row.combo.currentIndexChanged.connect(
            lambda _index: self._set(
                "away_only_when_unfocused_min", self.unfocused_row.combo.currentData()
            )
        )
        self.schedule_enabled_row.checkbox.toggled.connect(self._on_schedule_enabled)
        self.schedule_start_row.line_edit.editingFinished.connect(self._on_schedule_window)
        self.schedule_end_row.line_edit.editingFinished.connect(self._on_schedule_window)
        self.schedule_weekend_row.checkbox.toggled.connect(
            lambda value: self._set("away_schedule_weekend", value)
        )

        self.scheduled_enabled_row.checkbox.toggled.connect(
            lambda value: self._set("scheduled_enabled", value)
        )
        self.grace_row.combo.currentIndexChanged.connect(
            lambda _index: self._set(
                "scheduled_late_grace_min", self.grace_row.combo.currentData()
            )
        )
        self.scheduled_list.currentItemChanged.connect(self._on_scheduled_selected)
        self.remove_scheduled_button.clicked.connect(self._remove_scheduled)
        self.resend_button.clicked.connect(self._resend_scheduled)

    # --- handlers ------------------------------------------------------------
    def _set(self, attribute: str, value) -> None:
        setattr(self.model.settings, attribute, value)

    def _on_enabled(self, enabled: bool):
        self._set("enabled", enabled)
        self.set_dependent_enabled(enabled)

    def _on_delay_changed(self, _index):
        minimum = int(self.delay_min_row.combo.currentData())
        maximum = int(self.delay_max_row.combo.currentData())
        if maximum < minimum:
            maximum = minimum
            self.delay_max_row.combo.blockSignals(True)
            self.select_combo_value(self.delay_max_row.combo, maximum)
            self.delay_max_row.combo.blockSignals(False)
            maximum = int(self.delay_max_row.combo.currentData())
        self._set("delay_min_s", minimum)
        self._set("delay_max_s", maximum)

    def _on_away_text_changed(self):
        text = self.away_text_edit.toPlainText()
        self.away_text_count.setText(f"{len(text)}/{MAX_AWAY_TEXT_LENGTH}")
        try:
            self.model.save_away_text(text)
        except AutomationValidationError as error:
            if error.code == AutomationValidationError.TOO_LONG:
                self.away_text_error.setText(_("The reply is too long."))
            else:
                self.away_text_error.setText(_("Enter the reply text."))
            self.away_text_error.show()
            if error.code == AutomationValidationError.EMPTY_TEXT:
                self.model.settings.away_text = ""
            return
        self.away_text_error.hide()

    def _on_schedule_enabled(self, enabled: bool):
        self._set("away_schedule_enabled", enabled)
        self._set_schedule_rows_enabled(enabled)

    def _set_schedule_rows_enabled(self, enabled: bool):
        self.schedule_start_row.setEnabled(enabled)
        self.schedule_end_row.setEnabled(enabled)
        self.schedule_weekend_row.setEnabled(enabled)

    def _on_schedule_window(self):
        try:
            self.model.save_schedule_window(
                self.schedule_start_row.line_edit.text(),
                self.schedule_end_row.line_edit.text(),
            )
        except AutomationValidationError:
            self.show_schedule_error(_("Use the format HH:MM, for example 18:00."))
            return
        self.clear_schedule_error()
        settings = self.model.settings
        self.schedule_start_row.line_edit.setText(settings.away_schedule_start)
        self.schedule_end_row.line_edit.setText(settings.away_schedule_end)

    def _open_log(self):
        automation_logger()  # garante que o arquivo exista
        path = log_path()
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            except OSError:
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # --- lista de agendadas ----------------------------------------------------
    @staticmethod
    def status_label(status: str) -> str:
        labels = {
            STATUS_PENDING: _("pending"),
            STATUS_SENT: _("sent"),
            STATUS_FAILED: _("failed"),
            STATUS_EXPIRED: _("expired"),
        }
        return labels.get(status, status)

    def reload_scheduled_list(self, select_id: str | None = None):
        self.scheduled_list.blockSignals(True)
        self.scheduled_list.clear()
        selected = None
        for item in self.model.scheduled_items:
            label = "+{}  ·  {}  ·  {}".format(
                item.number,
                format_schedule_datetime(item.when),
                self.status_label(item.status),
            )
            if item.last_error and item.status != STATUS_SENT:
                label = f"{label} ({item.last_error})"
            entry = QListWidgetItem(label, self.scheduled_list)
            entry.setData(self.ITEM_ROLE, item.id)
            entry.setToolTip(item.text)
            if item.id == select_id:
                selected = entry
        self.scheduled_list.blockSignals(False)
        self.update_scheduled_empty_state()
        if selected is not None:
            self.scheduled_list.setCurrentItem(selected)
        # A QListWidget pode já ter definido um item corrente ao inserir;
        # sincroniza os botões com o estado real em vez de supor "nenhum".
        self._on_scheduled_selected(self.scheduled_list.currentItem(), None)

    def _current_scheduled(self):
        entry = self.scheduled_list.currentItem()
        if entry is None:
            return None
        item_id = entry.data(self.ITEM_ROLE)
        return self.model.settings.find_scheduled(item_id)

    def _on_scheduled_selected(self, current, _previous):
        item = self._current_scheduled() if current is not None else None
        self.remove_scheduled_button.setEnabled(item is not None)
        self.resend_button.setEnabled(
            item is not None and item.status in (STATUS_FAILED, STATUS_EXPIRED)
        )

    def _remove_scheduled(self):
        item = self._current_scheduled()
        if item is None:
            return
        self.model.remove_scheduled(item.id)
        self.reload_scheduled_list()

    def _resend_scheduled(self):
        item = self._current_scheduled()
        if item is None:
            return
        service = AutomationService.instance()
        if service is not None:
            service.scheduler.resend_now(item.id)
        else:
            self.model.settings.update_scheduled(
                item.id, status=STATUS_PENDING, attempts=0, last_error="",
                last_attempt=None,
            )
        self.reload_scheduled_list(select_id=item.id)
