"""Tests for inserting quick phrases into the WhatsApp Web composer."""

import json
import unittest
from unittest.mock import patch

from qt_test_case import QtTestCase
from zapzap.features.browser.web.page_controller import PageController


class InsertTextInComposerTests(QtTestCase):
    def _page(self):
        with patch.object(PageController, "__init__", lambda self, *a, **k: None):
            return PageController()

    def test_text_reaches_javascript_as_a_json_literal(self):
        page = self._page()
        text = "Olá! \"aspas\" 'simples' </script> \\ fim\nlinha 2"
        captured = {}

        def fake_run(script, callback=None):
            captured["script"] = script
            captured["callback"] = callback

        with patch.object(page, "runJavaScript", side_effect=fake_run):
            page.insert_text_in_composer(text)

        script = captured["script"]
        self.assertIn(json.dumps(text), script)
        self.assertNotIn("</script>)", script)
        self.assertIn("insertText", script)
        self.assertTrue(script.rstrip().endswith(");"))

    def test_script_never_triggers_send(self):
        page = self._page()
        captured = {}
        with patch.object(
            page, "runJavaScript",
            side_effect=lambda s, cb=None: captured.setdefault("script", s),
        ):
            page.insert_text_in_composer("qualquer texto")
        script = captured["script"].lower()
        for forbidden in ("keycode", "'enter'", "\"enter\"", ".click(", "keydown", "submit"):
            self.assertNotIn(forbidden, script)

    def test_missing_composer_shows_toast_and_reports_result(self):
        page = self._page()
        results = []
        toasts = []

        def fake_run(script, callback=None):
            callback("sem-compositor")

        with patch.object(page, "runJavaScript", side_effect=fake_run), patch.object(
            page, "show_toast", side_effect=lambda m, d=1000: toasts.append(m)
        ):
            page.insert_text_in_composer("x", results.append)

        self.assertEqual(results, ["sem-compositor"])
        self.assertEqual(len(toasts), 1)

    def test_success_does_not_toast(self):
        page = self._page()
        toasts = []
        with patch.object(
            page, "runJavaScript", side_effect=lambda s, cb=None: cb("ok")
        ), patch.object(page, "show_toast", side_effect=toasts.append):
            page.insert_text_in_composer("x")
        self.assertEqual(toasts, [])


if __name__ == "__main__":
    unittest.main()
