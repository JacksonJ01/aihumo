from app.cognitive_games import MathGameDialog, SpellingBeeDialog, WordEntry, load_dictionary
from app.main_hub import MainHubDialog


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
    finally:
        dialog.close()


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
