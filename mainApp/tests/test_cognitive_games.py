from app.cognitive_games import MathGameDialog, SpellingBeeDialog, WordEntry, load_dictionary
from app.main_hub import MainHubDialog
from app.preferences import DesktopPreferences, PreferenceStore
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog


def test_dictionary_loader_filters_duplicates_and_unusable_words(tmp_path):
    path = tmp_path / "dictionary.csv"
    path.write_text(
        "Word,POS,Definition\n"
        "Balance,noun,A steady condition.\n"
        "balance,verb,Duplicate entry.\n"
        "A 1,noun,Not a playable alphabetic word.\n"
        "supercalifragilisticexpialidocious,noun,Too long.\n"
        "motion,noun,The act of moving.\n",
        encoding="utf-8",
    )
    entries = load_dictionary(path)
    assert entries == (
        WordEntry("Balance", "A steady condition.", "noun"),
        WordEntry("motion", "The act of moving.", "noun"),
    )


def test_cognitive_games_share_settings_and_refresh_theme(qt_app, tmp_path, monkeypatch):
    store = PreferenceStore(tmp_path / "settings.json")
    store.save(DesktopPreferences(theme="Light", setup_completed=True))
    dialog = MathGameDialog(preferences=store)
    try:
        assert dialog.preference_store is store
        assert dialog.settings_button.isEnabled()
        assert "#f5f7fb" in dialog.styleSheet()
        store.save(DesktopPreferences(theme="Dark", setup_completed=True))
        monkeypatch.setattr("app.cognitive_games.PreferencesDialog.exec", lambda _self: QDialog.DialogCode.Accepted)
        dialog.open_settings()
        assert dialog.preferences.theme == "Dark"
        assert "#091426" in dialog.styleSheet()
    finally:
        dialog.close()


def test_spelling_bee_uses_loaded_words_and_scores_answer(qt_app, tmp_path):
    path = tmp_path / "dictionary.csv"
    path.write_text("Word,POS,Definition\nBalance,noun,A steady condition.\n", encoding="utf-8")
    dialog = SpellingBeeDialog()
    try:
        dialog.entries = load_dictionary(path)
        dialog.difficulty.setCurrentText("Medium")
        dialog.rounds.setValue(1)
        dialog.start_game()
        assert dialog.current is not None
        dialog.answer.setText(dialog.current.word)
        dialog.submit_answer()
        assert dialog.correct == 1
        assert "Correct" in dialog.feedback.text()
        dialog.submit_answer()
        assert dialog.correct == 1
    finally:
        dialog.close()


def test_spelling_bee_enter_submits_then_advances(qt_app):
    dialog = SpellingBeeDialog()
    try:
        dialog.entries = (
            WordEntry("motion", "The act of moving."),
            WordEntry("rhythm", "A repeating pattern."),
        )
        dialog.difficulty.setCurrentText("Medium")
        dialog.rounds.setValue(2)
        dialog.start_game()
        first = dialog.current
        dialog.answer.setText(first.word)
        dialog._answer_entered()
        assert dialog.correct == 1
        assert dialog.next_button.isEnabled()
        dialog._answer_entered()
        assert dialog.current is not first
        assert dialog.round_number == 2
        assert dialog.submit_button.isEnabled()
    finally:
        dialog.close()


def test_spelling_bee_real_enter_never_closes_dialog(qt_app):
    dialog = SpellingBeeDialog()
    try:
        dialog.entries = (WordEntry("motion", "The act of moving."),)
        dialog.difficulty.setCurrentText("Medium")
        dialog.rounds.setValue(1)
        dialog.show()
        dialog.start_game()
        dialog.answer.setText("motion")
        dialog.answer.setFocus()
        QTest.keyClick(dialog.answer, Qt.Key.Key_Return)
        qt_app.processEvents()
        assert dialog.isVisible()
        assert dialog.correct == 1
        assert dialog.next_button.isEnabled()

        # Return on the explicit Continue action completes the round but does
        # not accept/close the dialog itself.
        dialog.next_button.setFocus()
        QTest.keyClick(dialog.next_button, Qt.Key.Key_Return)
        qt_app.processEvents()
        assert dialog.isVisible()
        assert dialog.current is None
    finally:
        dialog.close()


def test_math_enter_and_ws_navigation_do_not_accept_dialog(qt_app):
    dialog = MathGameDialog()
    try:
        dialog.rounds.setValue(2)
        dialog.show()
        dialog.start_game()
        dialog.answer.setText(str(dialog.answer_value))
        dialog.answer.setFocus()
        QTest.keyClick(dialog.answer, Qt.Key.Key_Return)
        qt_app.processEvents()
        assert dialog.isVisible()
        assert dialog.correct == 1

        dialog.next_button.setFocus()
        QTest.keyClick(dialog, Qt.Key.Key_S)
        qt_app.processEvents()
        assert dialog.isVisible()
        assert dialog.round_number == 2

        # W and S remain ordinary characters while typing in a text field.
        dialog.answer.setText("")
        dialog.answer.setFocus()
        QTest.keyClicks(dialog.answer, "ws")
        assert dialog.answer.text() == "ws"
    finally:
        dialog.close()


def test_math_challenge_generates_all_operations_and_scores_answer(qt_app):
    dialog = MathGameDialog()
    try:
        for operation in ("Addition", "Subtraction", "Multiplication", "Division"):
            dialog.operation.setCurrentText(operation)
            text, answer = dialog._new_problem()
            assert "?" in text
            assert isinstance(answer, (int, float))
        dialog.rounds.setValue(1)
        dialog.start_game()
        dialog.answer.setText(str(dialog.answer_value))
        dialog.submit_answer()
        assert dialog.correct == 1
        dialog.submit_answer()
        assert dialog.correct == 1
    finally:
        dialog.close()


def test_cognitive_game_buttons_and_enter_workflow_are_safe(qt_app, monkeypatch):
    monkeypatch.setattr("app.cognitive_games.QFileDialog.getOpenFileName", lambda *args: ("", ""))

    spelling = SpellingBeeDialog()
    try:
        spelling.entries = (WordEntry("motion", "The act of moving."),)
        spelling.difficulty.setCurrentText("Medium")
        spelling.rounds.setValue(1)
        spelling.dictionary_button.click()
        spelling.start_button.click()
        spelling.answer.setText("motion")
        spelling.submit_button.click()
        assert spelling.correct == 1
        spelling.next_button.click()
        assert spelling.current is None
        spelling.back_button.click()
    finally:
        spelling.close()

    math = MathGameDialog()
    try:
        math.rounds.setValue(2)
        math.start_button.click()
        first_answer = math.answer_value
        math.answer.setText(str(first_answer))
        math._answer_entered()
        assert math.correct == 1
        math._answer_entered()
        assert math.round_number == 2
        math.answer.setText(str(math.answer_value))
        math.submit_button.click()
        assert math.correct == 2
        math.next_button.click()
        assert math.start_button.isEnabled()
        math.back_button.click()
    finally:
        math.close()


def test_hub_exposes_standalone_cognitive_games(qt_app):
    dialog = MainHubDialog()
    try:
        cognitive = {app.cognitive_game_id for app in dialog.apps if app.cognitive_game_id}
        assert cognitive == {"spelling_bee", "math_challenge"}
        assert "Cognitive Games" in dialog.category_descriptions

        cognitive_button = next(button for button in dialog.nav_buttons if button.text() == "Cognitive Games")
        cognitive_button.click()
        qt_app.processEvents()
        assert dialog.pages.currentIndex() == dialog.NAV_ITEMS.index("Cognitive Games")
        assert {card.app.id for card in dialog.category_grids["Cognitive Games"].cards} == {
            "sequence",
            "spelling_bee",
            "math_challenge",
        }
        assert all(card.filter_match for card in dialog.category_grids["Cognitive Games"].cards)
    finally:
        dialog.close()
