"""Tests for the scheduled-message service: due items, grace, retries."""

from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from qt_test_case import QtTestCase
from zapzap.core.config.settings.automation import (
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    AutomationSettings,
    ScheduledMessage,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.automation import scheduler
from zapzap.features.automation.scheduler import ScheduledSendService


class FakeRunner:
    def __init__(self):
        self.jobs = []

    def enqueue(self, job):
        self.jobs.append(job)


class FakePageController:
    def __init__(self):
        self.opened = []

    def xdg_open_chat(self, url):
        self.opened.append(url)


class ScheduledSendServiceTests(QtTestCase):
    def setUp(self):
        super().setUp()
        for key in AutomationSettings.ALL_KEYS:
            SettingsManager.remove(key)
        self.settings = AutomationSettings()
        self.settings.enabled = True
        self.settings.scheduled_enabled = True
        self.now = datetime(2026, 9, 23, 12, 0)
        self.runner = FakeRunner()
        self.service = ScheduledSendService(
            self.runner, settings=self.settings, now_fn=lambda: self.now,
        )
        log_patch = patch.object(scheduler, "log_event")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def _add(self, item_id, when, **kwargs):
        self.settings.add_scheduled(ScheduledMessage(
            item_id, "u1", "5581999999999", "Bom dia", when, **kwargs
        ))

    def test_disabled_scheduler_never_enqueues(self):
        self._add("a", self.now - timedelta(minutes=1))
        self.settings.scheduled_enabled = False
        self.assertEqual(self.service.tick(), [])
        self.settings.scheduled_enabled = True
        self.settings.enabled = False
        self.assertEqual(self.service.tick(), [])
        self.assertEqual(self.runner.jobs, [])

    def test_due_item_is_sent_by_deeplink_without_text_and_marked_sent(self):
        self._add("a", self.now - timedelta(minutes=1))
        self._add("b", self.now - timedelta(minutes=1))
        self.assertEqual(self.service.tick(), ["a"])
        # Nunca dois em voo.
        self.assertEqual(self.service.tick(), [])
        job = self.runner.jobs[0]
        page = FakePageController()
        job.open_chat(page)
        self.assertEqual(page.opened, ["https://web.whatsapp.com/send?phone=5581999999999"])
        self.assertEqual(job.text, "Bom dia")
        self.assertEqual(job.expected_digits, "5581999999999")
        job.on_done("ok")
        self.assertEqual(self.settings.find_scheduled("a").status, STATUS_SENT)
        self.assertEqual(self.service.tick(), ["b"])

    def test_late_item_expires_within_grace_rules(self):
        self._add("late", self.now - timedelta(minutes=61))
        self._add("ok", self.now - timedelta(minutes=59))
        self.assertEqual(self.service.tick(), ["ok"])
        self.assertEqual(self.settings.find_scheduled("late").status, STATUS_EXPIRED)

    def test_failures_retry_up_to_three_times_then_fail(self):
        self._add("a", self.now - timedelta(minutes=1))
        for attempt in range(1, 4):
            self.assertEqual(self.service.tick(), ["a"])
            self.runner.jobs[-1].on_done("chat-nao-abriu")
            item = self.settings.find_scheduled("a")
            self.assertEqual(item.attempts, attempt)
            self.assertEqual(item.last_error, "chat-nao-abriu")
            if attempt < 3:
                self.assertEqual(item.status, STATUS_PENDING)
                # Antes de 5 min não tenta de novo.
                self.assertEqual(self.service.tick(), [])
                self.now += timedelta(minutes=5, seconds=1)
        self.assertEqual(item.status, STATUS_FAILED)
        self.assertEqual(self.service.tick(), [])

    def test_hourly_limit_does_not_consume_an_attempt(self):
        self._add("a", self.now - timedelta(minutes=1))
        self.service.tick()
        self.runner.jobs[-1].on_done("limite-hora")
        item = self.settings.find_scheduled("a")
        self.assertEqual((item.status, item.attempts, item.last_error), (STATUS_PENDING, 0, "limite-hora"))

    def test_resend_now_rearms_failed_item(self):
        self._add("a", self.now - timedelta(hours=3), status=STATUS_FAILED, attempts=3)
        updated = self.service.resend_now("a")
        self.assertEqual((updated.status, updated.attempts, updated.when), (STATUS_PENDING, 0, self.now))
        self.assertEqual(self.service.tick(), ["a"])
        self.assertIsNone(self.service.resend_now("missing"))

    def test_invalid_stored_number_fails_immediately(self):
        self.settings.add_scheduled(ScheduledMessage(
            "bad", "u1", "999", "x", self.now - timedelta(minutes=1)
        ))
        self.assertEqual(self.service.tick(), [])
        self.assertEqual(self.settings.find_scheduled("bad").status, STATUS_FAILED)
        self.assertEqual(self.runner.jobs, [])


if __name__ == "__main__":
    unittest.main()
