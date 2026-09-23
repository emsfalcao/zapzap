"""Tests for the away-reply decision flow (all brakes) with a fake runner."""

from datetime import datetime
import unittest
from unittest.mock import patch

from qt_test_case import QtTestCase
from zapzap.core.config.settings.automation import AutomationSettings
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.automation import away_reply
from zapzap.features.automation.away_reply import AwayReplyService, conversation_key
from zapzap.features.notifications.notification_service import NotificationService
from zapzap.features.automation.service import AutomationService


class FakeNotification:
    def __init__(self, title="Alice", message="oi", tag=""):
        self._title, self._message, self._tag = title, message, tag
        self.clicks = 0

    def title(self):
        return self._title

    def message(self):
        return self._message

    def tag(self):
        return self._tag

    def click(self):
        self.clicks += 1


class FakeUser:
    id = "u1"


class FakePage:
    user = FakeUser()


class FakeRunner:
    def __init__(self):
        self.jobs = []

    def enqueue(self, job):
        self.jobs.append(job)


class FakeActivity:
    def __init__(self, idle=3600.0):
        self.idle = idle

    def idle_seconds(self):
        return self.idle


class AwayReplyServiceTests(QtTestCase):
    def setUp(self):
        super().setUp()
        for key in AutomationSettings.ALL_KEYS:
            SettingsManager.remove(key)
        self.settings = AutomationSettings()
        self.settings.enabled = True
        self.settings.away_enabled = True
        self.settings.away_text = "Estou ausente."
        self.runner = FakeRunner()
        self.activity = FakeActivity()
        self.limit_ok = True
        self.now = datetime(2026, 9, 23, 20, 0)  # quarta, 20h
        self.clock_value = 1_000_000.0
        self.service = AwayReplyService(
            self.runner,
            self.activity,
            limit_allows=lambda: self.limit_ok,
            settings=self.settings,
            clock=lambda: self.clock_value,
            now_fn=lambda: self.now,
        )
        self.log_patch = patch.object(away_reply, "log_event")
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)

    def test_conversation_key_prefers_tag_and_is_per_account(self):
        self.assertEqual(conversation_key("u1", FakeNotification(tag="chat-9")), "u1|chat-9")
        self.assertEqual(conversation_key("u1", FakeNotification(title="Alice")), "u1|Alice")
        self.assertEqual(conversation_key("u1", FakeNotification(title="")), "")

    def test_disabled_by_default_does_nothing(self):
        self.settings.enabled = False
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "desligado")
        self.settings.enabled = True
        self.settings.away_enabled = False
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "desligado")
        self.assertEqual(self.runner.jobs, [])

    def test_empty_text_blocks(self):
        self.settings.away_text = "  "
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "sem-texto")

    def test_schedule_window_blocks_outside_hours(self):
        self.settings.away_schedule_enabled = True
        self.now = datetime(2026, 9, 23, 12, 0)
        self.assertEqual(
            self.service.on_incoming(FakePage(), FakeNotification()), "fora-do-horario"
        )
        self.now = datetime(2026, 9, 23, 23, 0)
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "enfileirada")

    def test_active_user_blocks_unless_zero(self):
        self.activity.idle = 60.0
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "usuario-ativo")
        self.settings.away_only_when_unfocused_min = 0
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "enfileirada")

    def test_cooldown_after_successful_send_and_in_flight_dedup(self):
        notification = FakeNotification()
        self.assertEqual(self.service.on_incoming(FakePage(), notification), "enfileirada")
        self.assertEqual(self.service.on_incoming(FakePage(), notification), "ja-na-fila")
        job = self.runner.jobs[0]
        self.assertEqual(job.text, "Estou ausente.")
        self.assertEqual(job.expected_title, "Alice")
        self.assertTrue(job.skip_groups)
        self.assertTrue(job.close_after)
        job.open_chat(None)
        self.assertEqual(notification.clicks, 1)
        job.on_done("ok")
        self.assertEqual(self.service.on_incoming(FakePage(), notification), "cooldown")
        self.clock_value += 9 * 3600
        self.assertEqual(self.service.on_incoming(FakePage(), notification), "enfileirada")

    def test_failed_send_does_not_start_cooldown(self):
        notification = FakeNotification()
        self.service.on_incoming(FakePage(), notification)
        self.runner.jobs[0].on_done("chat-nao-abriu")
        self.assertEqual(self.service.on_incoming(FakePage(), notification), "enfileirada")

    def test_hourly_limit_blocks(self):
        self.limit_ok = False
        self.assertEqual(self.service.on_incoming(FakePage(), FakeNotification()), "limite-hora")


class NotificationHookTests(QtTestCase):
    def test_hook_runs_before_notification_early_returns(self):
        SettingsManager.set("notification/app", False)
        self.addCleanup(SettingsManager.remove, "notification/app")
        calls = []
        with patch.object(
            AutomationService, "notify_incoming",
            side_effect=lambda page, notification: calls.append(notification),
        ), patch.object(NotificationService, "_select_backend", return_value=None):
            service = NotificationService()
            notification = FakeNotification()
            service.notify(FakePage(), notification)
        self.assertEqual(calls, [notification])

    def test_hook_is_a_no_op_without_a_service_instance(self):
        AutomationService._instance = None
        self.assertIsNone(AutomationService.notify_incoming(FakePage(), FakeNotification()))


if __name__ == "__main__":
    unittest.main()
