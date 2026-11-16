"""Standalone spelling and mathematics games for the AIHuMo Main Hub.

These games intentionally do not require pose features.  They share the Hub
and scoring style, but remain useful when a user wants a cognitive activity
without loading a video.
"""
from __future__ import annotations

import csv
import random
import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


WORD_RE = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)?$")
FALLBACK_WORDS = (
    ("balance", "A steady condition in which different parts are equal or stable."),
    ("motion", "The act or process of changing position."),
    ("rhythm", "A regular pattern of movement or sound."),
    ("target", "Something a person aims at or tries to reach."),
    ("skeleton", "The supporting framework of a body."),
    ("energy", "The ability to do work or cause change."),
    ("focus", "Close attention directed toward something."),
    ("velocity", "The speed and direction of moving something."),
)


@dataclass(frozen=True)
class WordEntry:
    word: str
    definition: str
    part_of_speech: str = ""


def load_dictionary(path: str | Path) -> tuple[WordEntry, ...]:
    """Load and clean a Word/POS/Definition CSV without retaining duplicates."""
    entries: list[WordEntry] = []
    seen: set[str] = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Word", "Definition"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError("Dictionary CSV must contain Word and Definition columns.")
        for row in reader:
            raw_word = str(row.get("Word", "")).strip()
            word = raw_word.replace(" ", "")
            if not word or not WORD_RE.fullmatch(word) or not 3 <= len(word) <= 14:
                continue
            key = word.casefold()
            if key in seen:
                continue
            definition = " ".join(str(row.get("Definition", "")).split())
            if not definition:
                continue
            seen.add(key)
            entries.append(WordEntry(word, definition, str(row.get("POS", "")).strip()))
    if not entries:
        raise ValueError("The dictionary did not contain usable words between 3 and 14 letters.")
    return tuple(entries)


def _difficulty_bounds(label: str) -> tuple[int, int]:
    return {"Easy": (3, 5), "Medium": (5, 8), "Hard": (8, 14)}.get(label, (3, 14))


class _GameDialog(QDialog):
    def _make_header(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        heading.addWidget(title_label, 1)
        self.back_button = QPushButton("Back to Hub Page")
        self.back_button.clicked.connect(self.close)
        heading.addWidget(self.back_button)
        layout.addLayout(heading)
        description = QLabel(subtitle)
        description.setWordWrap(True)
        layout.addWidget(description)
        return layout

    @staticmethod
    def _styled_feedback(label: QLabel) -> None:
        label.setWordWrap(True)
        label.setMinimumHeight(42)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)


class SpellingBeeDialog(_GameDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AIHuMo Cognitive Game — Spelling Bee")
        self.resize(820, 620)
        self.entries = tuple(WordEntry(word, definition) for word, definition in FALLBACK_WORDS)
        self.rng = random.Random()
        self.current: WordEntry | None = None
        self.round_number = 0
        self.correct = 0
        self._round_entries: list[WordEntry] = []

        layout = self._make_header(
            "Spelling Bee",
            "Hear or read a definition, then spell the word. Your dictionary is filtered into playable words and duplicate definitions are removed.",
        )
        source = QGroupBox("Dictionary source")
        source_row = QHBoxLayout(source)
        self.dictionary_path = QLineEdit()
        self.dictionary_path.setPlaceholderText("Optional CSV: Word, POS, Definition")
        self.dictionary_button = QPushButton("Load dictionary…")
        self.dictionary_button.clicked.connect(self.choose_dictionary)
        source_row.addWidget(self.dictionary_path, 1)
        source_row.addWidget(self.dictionary_button)
        layout.addWidget(source)

        controls = QFormLayout()
        self.difficulty = QComboBox(); self.difficulty.addItems(("Easy", "Medium", "Hard"))
        self.rounds = QSpinBox(); self.rounds.setRange(1, 50); self.rounds.setValue(10)
        controls.addRow("Difficulty", self.difficulty)
        controls.addRow("Rounds", self.rounds)
        layout.addLayout(controls)

        self.progress = QLabel("Press Start to begin.")
        self.progress.setStyleSheet("font-weight: 700;")
        layout.addWidget(self.progress)
        self.definition = QLabel("Your definition will appear here.")
        self.definition.setObjectName("cognitivePrompt")
        self.definition.setWordWrap(True)
        self.definition.setMinimumHeight(120)
        self.definition.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.definition)
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("Type the spelling here…")
        self.answer.returnPressed.connect(self._answer_entered)
        layout.addWidget(self.answer)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_game)
        self.submit_button = QPushButton("Submit spelling")
        self.submit_button.clicked.connect(self.submit_answer)
        self.submit_button.setEnabled(False)
        self.next_button = QPushButton("Next word")
        self.next_button.clicked.connect(self.next_word)
        self.next_button.setEnabled(False)
        for button in (self.start_button, self.submit_button, self.next_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.feedback = QLabel()
        self._styled_feedback(self.feedback)
        layout.addWidget(self.feedback)

    def choose_dictionary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose dictionary CSV", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            entries = load_dictionary(path)
        except (OSError, ValueError) as exc:
            self.feedback.setText(f"Could not load dictionary: {exc}")
            return
        self.entries = entries
        self.dictionary_path.setText(path)
        self.feedback.setText(f"Loaded {len(entries):,} playable words.")

    def start_game(self) -> None:
        low, high = _difficulty_bounds(self.difficulty.currentText())
        candidates = [entry for entry in self.entries if low <= len(entry.word) <= high]
        if not candidates:
            self.feedback.setText("No words match this difficulty in the loaded dictionary.")
            return
        self._round_entries = self.rng.sample(candidates, min(self.rounds.value(), len(candidates)))
        self.round_number = 0
        self.correct = 0
        self.start_button.setEnabled(False)
        self.difficulty.setEnabled(False)
        self.rounds.setEnabled(False)
        self.next_word()

    def next_word(self) -> None:
        if self.round_number >= len(self._round_entries):
            self.current = None
            self.definition.setText("Spelling Bee complete")
            self.progress.setText(f"Final score: {self.correct}/{len(self._round_entries)}")
            self.submit_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.start_button.setEnabled(True)
            self.difficulty.setEnabled(True)
            self.rounds.setEnabled(True)
            return
        self.current = self._round_entries[self.round_number]
        self.round_number += 1
        self.definition.setText(self.current.definition)
        self.progress.setText(f"Word {self.round_number} of {len(self._round_entries)}")
        self.answer.clear(); self.answer.setFocus()
        self.feedback.clear()
        self.submit_button.setEnabled(True)
        self.next_button.setEnabled(False)
        QApplication.beep()

    def submit_answer(self) -> None:
        if self.current is None or not self.submit_button.isEnabled():
            return
        guess = self.answer.text().strip().casefold()
        expected = self.current.word.casefold()
        if guess == expected:
            self.correct += 1
            self.feedback.setText("Correct!")
        else:
            self.feedback.setText(f"The answer was: {self.current.word}")
        self.submit_button.setEnabled(False)
        self.next_button.setEnabled(True)

    def _answer_entered(self) -> None:
        """Use Enter for the currently available spelling action.

        This prevents a second Enter press from scoring the same word twice and
        makes keyboard-only play follow Submit -> Next -> Submit naturally.
        """
        if self.submit_button.isEnabled():
            self.submit_answer()
        elif self.next_button.isEnabled():
            self.next_word()


class MathGameDialog(_GameDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AIHuMo Cognitive Game — Math Challenge")
        self.resize(820, 620)
        self.rng = random.Random()
        self.round_number = 0
        self.correct = 0
        self.answer_value: int | float | None = None
        self.total_rounds = 10

        layout = self._make_header(
            "Math Challenge",
            "Solve generated addition, subtraction, multiplication, or division problems. Difficulty controls the number range and operation complexity.",
        )
        controls = QFormLayout()
        self.operation = QComboBox(); self.operation.addItems(("Mixed", "Addition", "Subtraction", "Multiplication", "Division"))
        self.difficulty = QComboBox(); self.difficulty.addItems(("Easy", "Medium", "Hard"))
        self.rounds = QSpinBox(); self.rounds.setRange(1, 50); self.rounds.setValue(10)
        controls.addRow("Operation", self.operation)
        controls.addRow("Difficulty", self.difficulty)
        controls.addRow("Rounds", self.rounds)
        layout.addLayout(controls)
        self.progress = QLabel("Press Start to begin."); self.progress.setStyleSheet("font-weight: 700;")
        layout.addWidget(self.progress)
        self.problem = QLabel("?")
        self.problem.setStyleSheet("font-size: 42px; font-weight: 700;")
        self.problem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.problem.setMinimumHeight(150)
        layout.addWidget(self.problem)
        self.answer = QLineEdit(); self.answer.setPlaceholderText("Enter your answer…")
        self.answer.returnPressed.connect(self._answer_entered)
        layout.addWidget(self.answer)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start"); self.start_button.clicked.connect(self.start_game)
        self.submit_button = QPushButton("Submit answer"); self.submit_button.clicked.connect(self.submit_answer); self.submit_button.setEnabled(False)
        self.next_button = QPushButton("Next problem"); self.next_button.clicked.connect(self.next_problem); self.next_button.setEnabled(False)
        for button in (self.start_button, self.submit_button, self.next_button): actions.addWidget(button)
        layout.addLayout(actions)
        self.feedback = QLabel(); self._styled_feedback(self.feedback); layout.addWidget(self.feedback)

    def _new_problem(self) -> tuple[str, int | float]:
        level = self.difficulty.currentText()
        max_value = {"Easy": 20, "Medium": 100, "Hard": 1000}[level]
        operation = self.operation.currentText()
        if operation == "Mixed":
            operation = self.rng.choice(("Addition", "Subtraction", "Multiplication", "Division"))
        if operation == "Addition":
            a, b = self.rng.randint(0, max_value), self.rng.randint(0, max_value)
            return f"{a} + {b} = ?", a + b
        if operation == "Subtraction":
            a, b = sorted((self.rng.randint(0, max_value), self.rng.randint(0, max_value)), reverse=True)
            return f"{a} − {b} = ?", a - b
        if operation == "Multiplication":
            factor = 10 if level == "Easy" else 15 if level == "Medium" else 25
            a, b = self.rng.randint(0, factor), self.rng.randint(0, factor)
            return f"{a} × {b} = ?", a * b
        divisor = self.rng.randint(1, 10 if level == "Easy" else 20 if level == "Medium" else 50)
        quotient = self.rng.randint(1, max(1, max_value // divisor))
        return f"{divisor * quotient} ÷ {divisor} = ?", quotient

    def start_game(self) -> None:
        self.total_rounds = self.rounds.value()
        self.round_number = 0; self.correct = 0
        self.start_button.setEnabled(False); self.operation.setEnabled(False)
        self.difficulty.setEnabled(False); self.rounds.setEnabled(False)
        self.next_problem()

    def next_problem(self) -> None:
        if self.round_number >= self.total_rounds:
            self.problem.setText("Complete")
            self.progress.setText(f"Final score: {self.correct}/{self.total_rounds}")
            self.submit_button.setEnabled(False); self.next_button.setEnabled(False); self.start_button.setEnabled(True)
            self.operation.setEnabled(True); self.difficulty.setEnabled(True); self.rounds.setEnabled(True)
            return
        self.round_number += 1
        text, self.answer_value = self._new_problem()
        self.problem.setText(text); self.progress.setText(f"Problem {self.round_number} of {self.total_rounds}")
        self.answer.clear(); self.answer.setFocus(); self.feedback.clear()
        self.submit_button.setEnabled(True); self.next_button.setEnabled(False)

    def submit_answer(self) -> None:
        if self.answer_value is None or not self.submit_button.isEnabled():
            return
        try:
            guess = float(self.answer.text().strip())
        except ValueError:
            self.feedback.setText("Enter a number.")
            return
        if abs(guess - float(self.answer_value)) < 1e-9:
            self.correct += 1; self.feedback.setText("Correct!")
        else:
            self.feedback.setText(f"The answer was {self.answer_value}.")
        self.submit_button.setEnabled(False); self.next_button.setEnabled(True)

    def _answer_entered(self) -> None:
        """Use Enter for Submit or Next without scoring a problem twice."""
        if self.submit_button.isEnabled():
            self.submit_answer()
        elif self.next_button.isEnabled():
            self.next_problem()


class CognitiveGameDialog(QDialog):
    """Small dispatcher so the Hub can launch standalone cognitive apps."""

    def __new__(cls, game_id: str, parent=None):
        if game_id == "spelling_bee":
            return SpellingBeeDialog(parent)
        if game_id == "math_challenge":
            return MathGameDialog(parent)
        raise ValueError(f"Unknown cognitive game: {game_id}")
