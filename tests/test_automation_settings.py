"""Tests for the automation settings domain and its Settings page."""

from datetime import datetime, timedelta
import unittest

from qt_test_case import QtTestCase
from zapzap.core.config.settings.automation import (
    MAX_SCHEDULED_ATTEMPTS,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    AutomationSettings,
    AutomationValidationError,
    HourlyLimit,
    ReplyCooldown,
    ScheduledMessage,
    due_scheduled_items,
    is_within_daily_window,
    parse_schedule_datetime,
    parse_time_hhmm,
    split_e164,
    validate_away_text,
    validate_e164_number,
    validate_scheduled_message,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.settings.pages.automation.controller import (
    AutomationSettingsController,
)


def clear_automation_keys():
    for key in AutomationSettings.ALL_KEYS:
        SettingsManager.remove(key)


class TimeParsingTests(unittest.TestCase):
    def test_parse_time_accepts_valid_and_rejects_invalid(self):
        self.assertEqual(parse_time_hhmm(" 8:05 "), (8, 5))
        self.assertEqual(parse_time_hhmm("23:59"), (23, 59))
        for bad in ("", "24:00", "12:60", "8h", "ab:cd", "1:2"):
            with self.subTest(value=bad):
                with self.assertRaises(AutomationValidationError) as raised:
                    parse_time_hhmm(bad)
                self.assertEqual(
                    raised.exception.code, AutomationValidationError.INVALID_TIME
                )

    def test_parse_schedule_datetime(self):
        self.assertEqual(
            parse_schedule_datetime("2026-12-31 09:05"),
            datetime(2026, 12, 31, 9, 5),
        )
        for bad in ("2026-13-01 09:00", "31/12/2026 09:00", "2026-12-31", ""):
            with self.subTest(value=bad):
                with self.assertRaises(AutomationValidationError):
                    parse_schedule_datetime(bad)


class DailyWindowTests(unittest.TestCase):
    def test_window_crossing_midnight(self):
        # Quarta-feira, 2026-09-23.
        inside_evening = datetime(2026, 9, 23, 19, 0)
        inside_morning = datetime(2026, 9, 24, 7, 59)
        outside = datetime(2026, 9, 23, 12, 0)
        self.assertTrue(is_within_daily_window(inside_evening, "18:00", "08:00"))
        self.assertTrue(is_within_daily_window(inside_morning, "18:00", "08:00"))
        self.assertFalse(is_within_daily_window(outside, "18:00", "08:00"))
        # Limites: início inclusivo, fim exclusivo.
        self.assertTrue(is_within_daily_window(datetime(2026, 9, 23, 18, 0), "18:00", "08:00"))
        self.assertFalse(is_within_daily_window(datetime(2026, 9, 24, 8, 0), "18:00", "08:00"))

    def test_window_same_day_and_full_day(self):
        self.assertTrue(is_within_daily_window(datetime(2026, 9, 23, 10, 0), "09:00", "17:00"))
        self.assertFalse(is_within_daily_window(datetime(2026, 9, 23, 18, 0), "09:00", "17:00"))
        self.assertTrue(is_within_daily_window(datetime(2026, 9, 23, 3, 0), "00:00", "00:00"))

    def test_weekend_counts_entirely_when_enabled(self):
        saturday_noon = datetime(2026, 9, 26, 12, 0)
        self.assertFalse(is_within_daily_window(saturday_noon, "18:00", "08:00"))
        self.assertTrue(
            is_within_daily_window(saturday_noon, "18:00", "08:00", include_weekend=True)
        )


class NumberAndTextTests(unittest.TestCase):
    def test_split_and_validate_e164(self):
        self.assertEqual(split_e164("+55 (81) 99999-9999"), ("55", "81999999999"))
        self.assertEqual(split_e164("+1 415 555 0100"), ("1", "4155550100"))
        target = validate_e164_number("+5581999999999")
        self.assertEqual(target.normalized_phone, "5581999999999")
        for bad in ("", "abc", "+999 1234", "+55"):
            with self.subTest(value=bad):
                with self.assertRaises(AutomationValidationError) as raised:
                    validate_e164_number(bad)
                self.assertEqual(
                    raised.exception.code, AutomationValidationError.INVALID_NUMBER
                )

    def test_away_text_rules(self):
        self.assertEqual(validate_away_text("Olá"), "Olá")
        with self.assertRaises(AutomationValidationError) as raised:
            validate_away_text("   ")
        self.assertEqual(raised.exception.code, AutomationValidationError.EMPTY_TEXT)
        with self.assertRaises(AutomationValidationError) as raised:
            validate_away_text("x" * 1001)
        self.assertEqual(raised.exception.code, AutomationValidationError.TOO_LONG)

    def test_scheduled_message_validation(self):
        now = datetime(2026, 9, 23, 10, 0)
        item = validate_scheduled_message(
            "u1", "+55 81 99999-9999", "Oi", "2026-09-23 10:30", now=now
        )
        self.assertEqual(item.number, "5581999999999")
        self.assertEqual(item.status, STATUS_PENDING)
        self.assertEqual(item.when, datetime(2026, 9, 23, 10, 30))
        self.assertEqual(item.created_at, now)
        with self.assertRaises(AutomationValidationError) as raised:
            validate_scheduled_message("u1", "+5581999999999", "Oi", "2026-09-23 09:00", now=now)
        self.assertEqual(
            raised.exception.code, AutomationValidationError.DATETIME_IN_PAST
        )
        with self.assertRaises(AutomationValidationError) as raised:
            validate_scheduled_message("u1", "+5581999999999", "x" * 5000, "2026-09-23 11:00", now=now)
        self.assertEqual(raised.exception.code, AutomationValidationError.TOO_LONG)


class DueItemsTests(unittest.TestCase):
    def _item(self, item_id, when, **kwargs):
        return ScheduledMessage(
            id=item_id, user_id="u", number="5581999999999", text="x", when=when,
            **kwargs,
        )

    def test_only_due_pending_items_are_sent_and_late_ones_expire(self):
        now = datetime(2026, 9, 23, 12, 0)
        items = [
            self._item("future", now + timedelta(minutes=5)),
            self._item("due", now - timedelta(minutes=1)),
            self._item("late", now - timedelta(minutes=61)),
            self._item("sent", now - timedelta(minutes=1), status=STATUS_SENT),
            self._item("failed", now - timedelta(minutes=1), status=STATUS_FAILED),
        ]
        to_send, to_expire = due_scheduled_items(items, now, late_grace_min=60)
        self.assertEqual([item.id for item in to_send], ["due"])
        self.assertEqual([item.id for item in to_expire], ["late"])

    def test_retry_waits_between_attempts(self):
        now = datetime(2026, 9, 23, 12, 0)
        recent = self._item(
            "recent", now - timedelta(minutes=2),
            attempts=1, last_attempt=now - timedelta(minutes=1),
        )
        old = self._item(
            "old", now - timedelta(minutes=10),
            attempts=1, last_attempt=now - timedelta(minutes=6),
        )
        to_send, _ = due_scheduled_items([recent, old], now, late_grace_min=60)
        self.assertEqual([item.id for item in to_send], ["old"])
        self.assertLess(MAX_SCHEDULED_ATTEMPTS, 10)


class LimitAndCooldownTests(unittest.TestCase):
    def test_hourly_limit_is_a_sliding_window(self):
        limit = HourlyLimit()
        base = 1_000_000.0
        for offset in range(10):
            limit.record(base + offset)
        self.assertFalse(limit.allows(10, base + 100))
        self.assertTrue(limit.allows(11, base + 100))
        # Uma hora depois do primeiro registro, a janela libera.
        self.assertTrue(limit.allows(10, base + 3601))
        self.assertEqual(limit.count(base + 3601 + 9), 0)

    def test_reply_cooldown(self):
        cooldown = ReplyCooldown()
        cooldown.mark("u|Alice", 1000.0)
        self.assertTrue(cooldown.is_cooling("u|Alice", 8 * 3600, 1000.0 + 3600))
        self.assertFalse(cooldown.is_cooling("u|Bob", 8 * 3600, 1000.0 + 3600))
        self.assertFalse(cooldown.is_cooling("u|Alice", 8 * 3600, 1000.0 + 9 * 3600))
        self.assertEqual(cooldown.replied, {})


class AutomationSettingsTests(QtTestCase):
    def setUp(self):
        super().setUp()
        clear_automation_keys()
        self.settings = AutomationSettings()

    def test_everything_defaults_to_off_and_conservative(self):
        settings = self.settings
        self.assertFalse(settings.enabled)
        self.assertFalse(settings.away_enabled)
        self.assertFalse(settings.scheduled_enabled)
        self.assertFalse(settings.away_schedule_enabled)
        self.assertEqual((settings.delay_min_s, settings.delay_max_s), (20, 60))
        self.assertEqual(settings.max_per_hour, 10)
        self.assertEqual(settings.away_cooldown_h, 8)
        self.assertTrue(settings.away_skip_groups)
        self.assertEqual(settings.away_only_when_unfocused_min, 5)
        self.assertEqual(
            (settings.away_schedule_start, settings.away_schedule_end),
            ("18:00", "08:00"),
        )
        self.assertTrue(settings.away_schedule_weekend)
        self.assertEqual(settings.scheduled_late_grace_min, 60)
        self.assertEqual(settings.scheduled_items, [])

    def test_time_setters_normalize_and_bad_storage_falls_back(self):
        self.settings.away_schedule_start = "8:05"
        self.assertEqual(self.settings.away_schedule_start, "08:05")
        SettingsManager.set("automation/away/schedule_end", "garbage")
        self.assertEqual(self.settings.away_schedule_end, "08:00")

    def test_scheduled_items_round_trip_and_updates(self):
        when = datetime(2026, 9, 23, 10, 30)
        item = ScheduledMessage("abc", "u1", "5581999999999", "Olá — “tudo” 😀", when)
        self.settings.add_scheduled(item)
        loaded = self.settings.scheduled_items
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].text, "Olá — “tudo” 😀")
        self.assertEqual(loaded[0].when, when)
        updated = self.settings.update_scheduled(
            "abc", status=STATUS_EXPIRED, attempts=2, last_error="chat-nao-abriu"
        )
        self.assertEqual(updated.status, STATUS_EXPIRED)
        self.assertEqual(self.settings.find_scheduled("abc").attempts, 2)
        self.settings.remove_scheduled("abc")
        self.assertEqual(self.settings.scheduled_items, [])

    def test_corrupted_storage_is_ignored(self):
        SettingsManager.set("automation/scheduled/items", "{not json")
        self.assertEqual(self.settings.scheduled_items, [])
        SettingsManager.set("automation/scheduled/items", '[{"id": "", "texto": "x"}, 5]')
        self.assertEqual(self.settings.scheduled_items, [])
        SettingsManager.set("automation/sent_timestamps", "oops")
        self.assertEqual(self.settings.load_hourly_limit().timestamps, [])
        SettingsManager.set("automation/away/replied", "[1,2]")
        self.assertEqual(self.settings.load_reply_cooldown().replied, {})

    def test_limit_and_cooldown_persist(self):
        limit = self.settings.load_hourly_limit()
        limit.record(5.0)
        self.settings.save_hourly_limit(limit)
        self.assertEqual(self.settings.load_hourly_limit().timestamps, [5.0])
        cooldown = self.settings.load_reply_cooldown()
        cooldown.mark("u|Alice", 7.0)
        self.settings.save_reply_cooldown(cooldown)
        self.assertEqual(self.settings.load_reply_cooldown().replied, {"u|Alice": 7.0})


class AutomationSettingsUiTests(QtTestCase):
    def setUp(self):
        super().setUp()
        clear_automation_keys()

    def test_master_switch_persists_and_gates_sections(self):
        page = AutomationSettingsController()
        self.assertFalse(page.enabled_row.checkbox.isChecked())
        self.assertFalse(page.away_section.isEnabled())
        page.enabled_row.checkbox.setChecked(True)
        self.assertTrue(AutomationSettings().enabled)
        self.assertTrue(page.away_section.isEnabled())
        self.assertTrue(page.scheduled_section.isEnabled())

    def test_warning_box_is_present(self):
        page = AutomationSettingsController()
        self.assertEqual(page.warning_box.property("kind"), "warning")

    def test_combos_and_text_persist(self):
        page = AutomationSettingsController()
        page.select_combo_value(page.max_per_hour_row.combo, 5)
        page.select_combo_value(page.cooldown_row.combo, 24)
        page.select_combo_value(page.unfocused_row.combo, 0)
        page.select_combo_value(page.grace_row.combo, 1440)
        page.away_text_edit.setPlainText("Estou ausente.")
        settings = AutomationSettings()
        self.assertEqual(settings.max_per_hour, 5)
        self.assertEqual(settings.away_cooldown_h, 24)
        self.assertEqual(settings.away_only_when_unfocused_min, 0)
        self.assertEqual(settings.scheduled_late_grace_min, 1440)
        self.assertEqual(settings.away_text, "Estou ausente.")

    def test_delay_max_never_below_min(self):
        page = AutomationSettingsController()
        page.select_combo_value(page.delay_min_row.combo, 60)
        page.select_combo_value(page.delay_max_row.combo, 30)
        settings = AutomationSettings()
        self.assertGreaterEqual(settings.delay_max_s, settings.delay_min_s)

    def test_invalid_time_shows_error_and_keeps_previous(self):
        page = AutomationSettingsController()
        page.schedule_start_row.line_edit.setText("25:00")
        page.schedule_start_row.line_edit.editingFinished.emit()
        self.assertFalse(page.schedule_error.isHidden())
        self.assertEqual(AutomationSettings().away_schedule_start, "18:00")
        page.schedule_start_row.line_edit.setText("19:30")
        page.schedule_start_row.line_edit.editingFinished.emit()
        self.assertTrue(page.schedule_error.isHidden())
        self.assertEqual(AutomationSettings().away_schedule_start, "19:30")

    def test_scheduled_list_remove_and_resend(self):
        settings = AutomationSettings()
        settings.enabled = True  # a seção fica desabilitada com o interruptor geral off
        when = datetime(2026, 9, 23, 10, 30)
        settings.add_scheduled(
            ScheduledMessage("a1", "u1", "5581999999999", "x", when, status=STATUS_FAILED)
        )
        settings.add_scheduled(
            ScheduledMessage("a2", "u1", "5581888888888", "y", when, status=STATUS_PENDING)
        )
        page = AutomationSettingsController()
        self.assertEqual(page.scheduled_list.count(), 2)
        page.scheduled_list.setCurrentRow(0)
        self.assertTrue(page.resend_button.isEnabled())
        page.resend_button.click()
        self.assertEqual(settings.find_scheduled("a1").status, STATUS_PENDING)
        page.scheduled_list.setCurrentRow(1)
        self.assertFalse(page.resend_button.isEnabled())
        page.remove_scheduled_button.click()
        self.assertEqual(page.scheduled_list.count(), 1)
        self.assertEqual([item.id for item in settings.scheduled_items], ["a1"])


if __name__ == "__main__":
    unittest.main()
