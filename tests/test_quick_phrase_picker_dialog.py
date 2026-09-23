"""Tests for the quick phrase picker dialog."""

import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from qt_test_case import QtTestCase
from zapzap.core.config.settings.quick_phrases import QuickPhrase
from zapzap.ui.components.quick_phrase_picker_dialog import (
    QuickPhrasePickerDialog,
)


PHRASES = [
    QuickPhrase("horario", "Horário", "Atendemos das 8h às 18h."),
    QuickPhrase("ola", "Saudação", "Olá! Como posso ajudar?"),
    QuickPhrase("pix", "", "Nossa chave PIX é o CNPJ."),
]


class QuickPhrasePickerDialogTests(QtTestCase):
    def test_lists_all_phrases_and_previews_the_first(self):
        dialog = QuickPhrasePickerDialog(phrases=PHRASES)
        self.assertEqual(dialog.phrase_list.count(), 3)
        self.assertEqual(dialog.preview.toPlainText(), PHRASES[0].text)
        self.assertTrue(dialog.insert_button.isEnabled())
        self.assertTrue(dialog.empty_label.isHidden() or not dialog.empty_label.isVisible())

    def test_search_filters_by_shortcut_title_or_text(self):
        dialog = QuickPhrasePickerDialog(phrases=PHRASES)
        dialog.search_edit.setText("/PIX")
        self.assertEqual(dialog.phrase_list.count(), 1)
        self.assertEqual(dialog.preview.toPlainText(), PHRASES[2].text)
        dialog.search_edit.setText("saudação")
        self.assertEqual(dialog.phrase_list.count(), 1)
        dialog.search_edit.setText("ajudar")
        self.assertEqual(dialog.phrase_list.count(), 1)
        dialog.search_edit.setText("nada-disso")
        self.assertEqual(dialog.phrase_list.count(), 0)
        self.assertFalse(dialog.insert_button.isEnabled())

    def test_enter_in_search_emits_selected_text_and_accepts(self):
        dialog = QuickPhrasePickerDialog(phrases=PHRASES)
        received = []
        dialog.phrase_chosen.connect(received.append)
        dialog.search_edit.setText("ola")
        QTest.keyClick(dialog.search_edit, Qt.Key.Key_Return)
        self.assertEqual(received, [PHRASES[1].text])
        self.assertEqual(dialog.chosen_text, PHRASES[1].text)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_escape_rejects_without_choosing(self):
        dialog = QuickPhrasePickerDialog(phrases=PHRASES)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertIsNone(dialog.chosen_text)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

    def test_empty_list_disables_insert(self):
        dialog = QuickPhrasePickerDialog(phrases=[])
        self.assertFalse(dialog.insert_button.isEnabled())
        self.assertIsNone(dialog.chosen_text)


if __name__ == "__main__":
    unittest.main()
