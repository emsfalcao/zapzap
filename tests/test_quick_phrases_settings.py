"""Tests for the quick phrases (frases prontas) settings and storage."""

import unittest

from qt_test_case import QtTestCase
from zapzap.core.config.settings.quick_phrases import (
    QuickPhrase,
    QuickPhraseValidationError,
    QuickPhrasesSettings,
    normalize_shortcut,
    validate_quick_phrase,
)
from zapzap.core.config.settings_manager import SettingsManager
from zapzap.features.settings.pages.quick_phrases.controller import (
    QuickPhrasesSettingsController,
)


class QuickPhrasesDomainTests(unittest.TestCase):
    def test_shortcut_is_normalized(self):
        self.assertEqual(normalize_shortcut("  /Saudacao "), "saudacao")

    def test_validation_rejects_bad_shortcuts_and_empty_text(self):
        cases = {
            ("", "t", "x"): QuickPhraseValidationError.EMPTY_SHORTCUT,
            ("com espaço", "t", "x"): QuickPhraseValidationError.INVALID_SHORTCUT,
            ("ok", "t", "   "): QuickPhraseValidationError.EMPTY_TEXT,
            ("ok", "t", "x" * 5000): QuickPhraseValidationError.TOO_LONG,
        }
        for (shortcut, title, text), code in cases.items():
            with self.subTest(shortcut=shortcut, text=text[:8]):
                with self.assertRaises(QuickPhraseValidationError) as raised:
                    validate_quick_phrase(shortcut, title, text)
                self.assertEqual(raised.exception.code, code)

    def test_validation_rejects_duplicates_unless_editing_same(self):
        existing = [QuickPhrase("ola", "", "Olá!")]
        with self.assertRaises(QuickPhraseValidationError) as raised:
            validate_quick_phrase("ola", "", "x", existing=existing)
        self.assertEqual(
            raised.exception.code,
            QuickPhraseValidationError.DUPLICATED_SHORTCUT,
        )
        phrase = validate_quick_phrase(
            "ola", "", "x", existing=existing, ignore_shortcut="ola"
        )
        self.assertEqual(phrase.shortcut, "ola")


class QuickPhrasesSettingsTests(QtTestCase):
    def setUp(self):
        super().setUp()
        SettingsManager.remove("quick_phrases/items")
        SettingsManager.remove("quick_phrases/enabled")
        self.settings = QuickPhrasesSettings()

    def test_defaults(self):
        self.assertTrue(self.settings.enabled)
        self.assertEqual(self.settings.items, [])

    def test_upsert_remove_and_ordering_round_trip(self):
        self.settings.upsert(QuickPhrase("zeta", "Z", "último"))
        self.settings.upsert(QuickPhrase("alfa", "A", "primeiro"))
        self.assertEqual(
            [p.shortcut for p in self.settings.items], ["alfa", "zeta"]
        )
        self.settings.upsert(
            QuickPhrase("beta", "B", "renomeado"), replace_shortcut="zeta"
        )
        self.assertEqual(
            [p.shortcut for p in self.settings.items], ["alfa", "beta"]
        )
        self.assertEqual(self.settings.find("/BETA").text, "renomeado")
        self.settings.remove("alfa")
        self.assertEqual([p.shortcut for p in self.settings.items], ["beta"])

    def test_unicode_survives_storage(self):
        self.settings.upsert(QuickPhrase("acento", "Ç", "Olá — “tudo” bem? 😀"))
        self.assertEqual(self.settings.items[0].text, "Olá — “tudo” bem? 😀")

    def test_corrupted_storage_is_ignored(self):
        SettingsManager.set("quick_phrases/items", "{not json")
        self.assertEqual(self.settings.items, [])
        SettingsManager.set("quick_phrases/items", '[{"atalho": "", "texto": "x"}, 5]')
        self.assertEqual(self.settings.items, [])


class QuickPhrasesSettingsUiTests(QtTestCase):
    def setUp(self):
        super().setUp()
        SettingsManager.remove("quick_phrases/items")
        SettingsManager.remove("quick_phrases/enabled")

    def test_save_edit_and_remove_through_the_page(self):
        page = QuickPhrasesSettingsController()
        self.assertEqual(page.phrase_list.count(), 0)

        page.shortcut_edit.setText("Horario")
        page.title_edit.setText("Horário")
        page.text_edit.setPlainText("Atendemos das 8h às 18h.")
        page.save_button.click()

        self.assertTrue(page.error_label.isHidden())
        self.assertEqual(page.phrase_list.count(), 1)
        self.assertEqual(QuickPhrasesSettings().items[0].shortcut, "horario")

        # Editing the selected phrase keeps a single entry.
        page.text_edit.setPlainText("Atendemos das 8h às 17h.")
        page.save_button.click()
        self.assertEqual(page.phrase_list.count(), 1)
        self.assertEqual(
            QuickPhrasesSettings().items[0].text, "Atendemos das 8h às 17h."
        )

        page.remove_button.click()
        self.assertEqual(page.phrase_list.count(), 0)
        self.assertEqual(QuickPhrasesSettings().items, [])

    def test_invalid_input_shows_error_and_saves_nothing(self):
        page = QuickPhrasesSettingsController()
        page.shortcut_edit.setText("com espaço")
        page.text_edit.setPlainText("x")
        page.save_button.click()
        self.assertFalse(page.error_label.isHidden())
        self.assertEqual(QuickPhrasesSettings().items, [])

    def test_toggle_persists_and_disables_sections(self):
        page = QuickPhrasesSettingsController()
        page.enabled_row.checkbox.setChecked(False)
        self.assertFalse(QuickPhrasesSettings().enabled)
        self.assertFalse(page.list_section.isEnabled())
        self.assertFalse(page.editor_section.isEnabled())


if __name__ == "__main__":
    unittest.main()
