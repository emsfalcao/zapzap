"""Tests for the serialized automation runner with a scripted fake page."""

import json
import unittest

from PyQt6.QtCore import QCoreApplication, QDeadlineTimer, QEventLoop

from qt_test_case import QtTestCase
from zapzap.features.automation import dom
from zapzap.features.automation.runner import (
    STATUS_ACCOUNT_INACTIVE,
    STATUS_GROUP_SKIPPED,
    STATUS_LIMIT,
    AutomationRunner,
    SendJob,
)


def state(status="ok", header="", dialog="ok"):
    return json.dumps({"status": status, "header": header, "dialog": dialog})


class FakePage:
    """Answers each script kind from a queue of canned results."""

    def __init__(self, states=None, group="individual", insert="ok", click="ok"):
        self.states = list(states or [])
        self.group = group
        self.insert = insert
        self.click = click
        self.scripts = []
        self.inserted = []
        self.closed = 0

    def runJavaScript(self, script, callback=None):
        self.scripts.append(script)
        if "JSON.stringify" in script:
            result = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        elif json.dumps(dom.GROUP_ICON_SELECTOR) in script:
            result = self.group
        elif ".click()" in script:
            result = self.click
        else:
            result = "ok"
        if callback is not None:
            callback(result)

    def insert_text_in_composer(self, text, callback=None):
        self.inserted.append(text)
        if callback is not None:
            callback(self.insert)

    def close_conversation(self):
        self.closed += 1


class FakeWebView:
    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def wait_until(predicate, timeout_ms=3000):
    deadline = QDeadlineTimer(timeout_ms)
    loop = QEventLoop()
    while not predicate() and not deadline.hasExpired():
        loop.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        QCoreApplication.sendPostedEvents()
    return predicate()


class AutomationRunnerTests(QtTestCase):
    def _runner(self, page, gate=None):
        webviews = {"u1": FakeWebView(page)} if page is not None else {}
        return AutomationRunner(
            webview_provider=webviews.get,
            delay_range_provider=lambda: (0, 0),
            limit_gate=gate,
            step_delay_ms=(0, 0),
            poll_interval_ms=1,
            poll_timeout_ms=5,
            gap_between_jobs_ms=0,
        )

    def _job(self, results, opened, **kwargs):
        return SendJob(
            kind="teste",
            user_id="u1",
            target="Alice",
            text="Olá",
            open_chat=lambda page: opened.append(page),
            on_done=results.append,
            **kwargs,
        )

    def test_happy_path_opens_chat_inserts_and_clicks_send(self):
        page = FakePage(states=[state("ok", "Bob"), state("ok", "Alice")])
        runner = self._runner(page)
        results, opened = [], []
        runner.enqueue(self._job(results, opened, expected_title="Alice", close_after=True))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, ["ok"])
        self.assertEqual(opened, [page])
        self.assertEqual(page.inserted, ["Olá"])
        self.assertTrue(any(".click()" in script for script in page.scripts))
        self.assertTrue(wait_until(lambda: page.closed == 1))
        self.assertFalse(runner.busy)

    def test_not_logged_in_fails_before_touching_the_chat(self):
        page = FakePage(states=[state("nao-logado")])
        runner = self._runner(page)
        results, opened = [], []
        runner.enqueue(self._job(results, opened))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [dom.STATUS_NOT_LOGGED])
        self.assertEqual(opened, [])
        self.assertEqual(page.inserted, [])

    def test_chat_that_never_opens_times_out_without_sending(self):
        page = FakePage(states=[state("ok", "Bob")])
        runner = self._runner(page)
        results, opened = [], []
        runner.enqueue(self._job(results, opened, expected_title="Alice"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [dom.STATUS_CHAT_NOT_OPENED])
        self.assertEqual(page.inserted, [])

    def test_invalid_number_dialog_aborts(self):
        page = FakePage(states=[state("ok", "Bob"), state("ok", "Bob", "numero-invalido")])
        runner = self._runner(page)
        results = []
        runner.enqueue(self._job(results, [], expected_digits="5581999999999"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [dom.STATUS_INVALID_NUMBER])

    def test_expected_digits_match_header_or_header_change(self):
        page = FakePage(states=[state("ok", "Bob"), state("ok", "+55 81 99999-9999")])
        runner = self._runner(page)
        results = []
        runner.enqueue(self._job(results, [], expected_digits="5581999999999"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, ["ok"])

    def test_group_is_skipped_when_requested(self):
        page = FakePage(states=[state("ok", "Turma"), state("ok", "Turma")], group="grupo")
        runner = self._runner(page)
        results = []
        runner.enqueue(self._job(results, [], expected_title="Turma", skip_groups=True))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [STATUS_GROUP_SKIPPED])
        self.assertEqual(page.inserted, [])

    def test_missing_send_button_and_missing_composer_report_failures(self):
        page = FakePage(states=[state("ok", "Alice")], click="sem-botao-enviar")
        results = []
        runner = self._runner(page)
        runner.enqueue(self._job(results, [], expected_title="Alice"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [dom.STATUS_NO_SEND_BUTTON])

        page = FakePage(states=[state("ok", "Alice")], insert="sem-compositor")
        results = []
        runner = self._runner(page)
        runner.enqueue(self._job(results, [], expected_title="Alice"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [dom.STATUS_NO_COMPOSER])
        self.assertFalse(any(".click()" in script for script in page.scripts))

    def test_limit_gate_blocks_the_click(self):
        page = FakePage(states=[state("ok", "Alice")])
        runner = self._runner(page, gate=lambda: False)
        results = []
        runner.enqueue(self._job(results, [], expected_title="Alice"))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [STATUS_LIMIT])
        self.assertFalse(any(".click()" in script for script in page.scripts))

    def test_inactive_account_fails_clearly(self):
        runner = self._runner(None)
        results = []
        runner.enqueue(self._job(results, []))
        self.assertTrue(wait_until(lambda: results))
        self.assertEqual(results, [STATUS_ACCOUNT_INACTIVE])

    def test_jobs_run_one_at_a_time_in_order(self):
        page = FakePage(states=[state("ok", "Alice")])
        runner = self._runner(page)
        results = []
        order = []
        for name in ("a", "b", "c"):
            runner.enqueue(SendJob(
                kind="teste", user_id="u1", target=name, text=name,
                open_chat=lambda _page, n=name: order.append(n),
                expected_title="Alice",
                on_done=lambda status, n=name: results.append((n, status, runner.pending)),
            ))
        self.assertTrue(wait_until(lambda: len(results) == 3))
        self.assertEqual(order, ["a", "b", "c"])
        self.assertEqual([r[0] for r in results], ["a", "b", "c"])
        self.assertEqual(page.inserted, ["a", "b", "c"])

    def test_stop_drops_queue_and_ignores_late_callbacks(self):
        page = FakePage(states=[state("ok", "Alice")])
        runner = self._runner(page)
        results = []
        runner.enqueue(self._job(results, []))
        runner.enqueue(self._job(results, []))
        runner.stop()
        self.assertFalse(wait_until(lambda: results, timeout_ms=100))
        self.assertEqual(runner.pending, 0)


if __name__ == "__main__":
    unittest.main()
