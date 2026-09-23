"""Tests for the automation DOM scripts (json.dumps, statuses, no Enter)."""

import json
import unittest
from unittest.mock import patch

from qt_test_case import QtTestCase
from zapzap.features.automation import dom
from zapzap.features.browser.web.page_controller import PageController


FORBIDDEN_SEND_TOKENS = ("keycode", "'enter'", '"enter"', "keydown", "keypress", "submit")


class DomScriptTests(unittest.TestCase):
    def test_every_selector_reaches_javascript_as_a_json_literal(self):
        scripts = {
            "probe": dom.build_probe_script(),
            "header": dom.build_chat_header_script(),
            "state": dom.build_chat_state_script(),
            "group": dom.build_is_group_script(),
            "click": dom.build_click_send_script(),
            "dialog": dom.build_invalid_number_dialog_script(),
        }
        for name, script in scripts.items():
            with self.subTest(script=name):
                self.assertTrue(script.rstrip().endswith(";"))
                self.assertTrue(script.startswith("(function(){"))
        for name in ("probe", "state", "click"):
            self.assertIn(json.dumps(dom.LOGGED_IN_SELECTOR), scripts[name])
        self.assertIn(json.dumps(dom.SEND_BUTTON_PRIMARY_SELECTOR), scripts["click"])
        self.assertIn(json.dumps(dom.SEND_ICON_SELECTOR), scripts["click"])
        self.assertIn(json.dumps(dom.GROUP_ICON_SELECTOR), scripts["group"])
        for selector in dom.COMPOSER_SELECTORS:
            self.assertIn(json.dumps(selector), scripts["probe"])

    def test_click_script_only_clicks_and_never_synthesizes_enter(self):
        script = dom.build_click_send_script().lower()
        for forbidden in FORBIDDEN_SEND_TOKENS:
            self.assertNotIn(forbidden, script)
        self.assertIn(".click()", script)
        for status in (dom.STATUS_OK, dom.STATUS_NOT_LOGGED, dom.STATUS_NO_SEND_BUTTON):
            self.assertIn(json.dumps(status), dom.build_click_send_script())

    def test_probe_and_state_scripts_return_documented_statuses(self):
        probe = dom.build_probe_script()
        for status in (dom.STATUS_OK, dom.STATUS_NO_COMPOSER, dom.STATUS_NOT_LOGGED):
            self.assertIn(json.dumps(status), probe)
        state = dom.build_chat_state_script()
        self.assertIn("JSON.stringify", state)
        self.assertIn(json.dumps(dom.STATUS_INVALID_NUMBER), state)

    def test_parse_chat_state_is_tolerant(self):
        parsed = dom.parse_chat_state('{"status": "ok", "header": "Alice", "dialog": "ok"}')
        self.assertEqual(parsed, {"status": "ok", "header": "Alice", "dialog": "ok"})
        for bad in (None, "", "{bad", "[1]", 5):
            with self.subTest(value=bad):
                self.assertEqual(dom.parse_chat_state(bad)["status"], dom.STATUS_NOT_LOGGED)


class ShowToastTests(QtTestCase):
    def test_toast_message_is_a_json_literal(self):
        with patch.object(PageController, "__init__", lambda self, *a, **k: None):
            page = PageController()
        message = "Olá 'aspas' \"duplas\" </script> \\ fim"
        captured = {}
        with patch.object(
            page, "runJavaScript",
            side_effect=lambda script, cb=None: captured.setdefault("script", script),
        ):
            page.show_toast(message, 1500)
        script = captured["script"]
        self.assertIn(json.dumps(message), script)
        self.assertNotIn("innerText = '", script)
        self.assertIn("}, 1500);", script)


if __name__ == "__main__":
    unittest.main()
