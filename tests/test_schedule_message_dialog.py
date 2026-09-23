"""Tests for the schedule-message dialog (validation only, no persistence)."""

from datetime import datetime
from gettext import gettext as _
import unittest

from PyQt6.QtWidgets import QDialog

from qt_test_case import QtTestCase
from zapzap.core.config.settings.automation import STATUS_PENDING
from zapzap.ui.components.schedule_message_dialog import (
    ScheduleMessageDialog,
    default_schedule_time,
)


NOW = datetime(2026, 9, 23, 10, 12)


class DefaultTimeTests(unittest.TestCase):
    def test_next_full_hour_at_least_thirty_minutes_ahead(self):
        self.assertEqual(default_schedule_time(NOW), datetime(2026, 9, 23, 11, 0))
        self.assertEqual(
            default_schedule_time(datetime(2026, 9, 23, 10, 45)),
            datetime(2026, 9, 23, 12, 0),
        )
        self.assertEqual(
            default_schedule_time(datetime(2026, 9, 23, 23, 40)),
            datetime(2026, 9, 24, 1, 0),
        )


class ScheduleMessageDialogTests(QtTestCase):
    def _dialog(self, enabled=True):
        return ScheduleMessageDialog(
            user_id="u1", account_label="Loja", automation_enabled=enabled,
            now_fn=lambda: NOW,
        )

    def test_prefills_a_future_time_and_shows_the_account(self):
        dialog = self._dialog()
        self.assertEqual(dialog.when_edit.text(), "2026-09-23 11:00")
        self.assertIn("Loja", dialog.description_label.text())
        self.assertTrue(dialog.error_label.isHidden())

    def test_valid_input_returns_a_pending_item(self):
        dialog = self._dialog()
        received = []
        dialog.message_scheduled.connect(received.append)
        dialog.number_edit.setText("+55 (81) 99999-9999")
        dialog.text_edit.setPlainText("Bom dia!")
        dialog.when_edit.setText("2026-09-23 15:30")
        dialog.schedule_button.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        item = dialog.scheduled_message
        self.assertEqual(received, [item])
        self.assertEqual(item.user_id, "u1")
        self.assertEqual(item.number, "5581999999999")
        self.assertEqual(item.text, "Bom dia!")
        self.assertEqual(item.when, datetime(2026, 9, 23, 15, 30))
        self.assertEqual(item.status, STATUS_PENDING)

    def test_invalid_number_past_time_and_empty_text_show_errors(self):
        dialog = self._dialog()
        dialog.number_edit.setText("abc")
        dialog.text_edit.setPlainText("x")
        dialog.schedule_button.click()
        self.assertFalse(dialog.error_label.isHidden())
        self.assertIsNone(dialog.scheduled_message)

        dialog.number_edit.setText("+5581999999999")
        dialog.when_edit.setText("2026-09-23 09:00")
        dialog.schedule_button.click()
        self.assertFalse(dialog.error_label.isHidden())
        self.assertIsNone(dialog.scheduled_message)

        dialog.when_edit.setText("2026-09-23 12:00")
        dialog.text_edit.setPlainText("   ")
        dialog.schedule_button.click()
        self.assertIsNone(dialog.scheduled_message)
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_disabled_automation_is_flagged_in_the_dialog(self):
        # Compara pelo catálogo ativo para não depender do idioma do processo.
        dialog = self._dialog(enabled=False)
        self.assertEqual(dialog.info_title_label.text(), _("Automation is disabled"))
        dialog = self._dialog(enabled=True)
        self.assertEqual(dialog.info_title_label.text(), _("Unofficial automation"))


if __name__ == "__main__":
    unittest.main()
