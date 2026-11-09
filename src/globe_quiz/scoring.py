"""Score a quiz session by the difficulty of each question.

A correct answer is worth ``1 + difficulty``. A wrong answer is worth 0.
The session score is 100 times the points earned divided by the points
that were possible. A harder question is worth more, so missing it costs
more than missing an easy one.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from random import choice

import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.io_countries import project_root
from globe_quiz.quiz import KINDS, countries_for, generate_question
from globe_quiz.similarity import country_similarity

COLUMNS = [
    "session_id",
    "kind",
    "country_code",
    "difficulty",
    "realized_difficulty",
    "correct",
    "earned",
    "maximum",
]


def question_points(correct: bool, difficulty: float) -> tuple[float, float]:
    """Return the points earned and the maximum for one question.

    Parameters
    ----------
    correct : bool
        Whether the player chose the right option.
    difficulty : float
        Mean similarity of the three wrong answers, from 0 to 1.

    Returns
    -------
    tuple of float
        ``(earned, maximum)``. The maximum is ``1 + difficulty``.

    Raises
    ------
    RuntimeError
        ``difficulty`` is outside 0 to 1.
    """
    if not 0.0 <= float(difficulty) <= 1.0:
        raise RuntimeError("Difficulty must be between 0 and 1")
    maximum = 1.0 + float(difficulty)
    earned = maximum if correct else 0.0
    return earned, maximum


def session_score(results: list[tuple[bool, float]]) -> float:
    """Return the session score on a scale from 0 to 100.

    Parameters
    ----------
    results : list of tuple
        Each item is ``(correct, difficulty)``.

    Returns
    -------
    float
        ``100 * earned / maximum`` across the whole session.

    Raises
    ------
    RuntimeError
        The session has no questions.
    """
    if not results:
        raise RuntimeError("A session needs at least one question")
    earned = 0.0
    maximum = 0.0
    for correct, difficulty in results:
        points, cap = question_points(correct, difficulty)
        earned += points
        maximum += cap
    return 100.0 * earned / maximum


def attempts_path(root: Path | None = None) -> Path:
    """Return ``data/results/attempts.csv``, creating the directory if needed."""
    directory = (root or project_root()) / "data" / "results"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "attempts.csv"


def append_attempt(attempt: pd.DataFrame, path: Path | None = None) -> Path:
    """Append one session to the attempts file.

    Parameters
    ----------
    attempt : pandas.DataFrame
        One row per question, with the columns in ``COLUMNS``.
    path : pathlib.Path, optional
        Destination. Defaults to ``data/results/attempts.csv``.

    Returns
    -------
    pathlib.Path
        The file that was written. The file is not committed.
    """
    destination = path or attempts_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    attempt.to_csv(destination, mode="a", header=not destination.exists(), index=False)
    return destination


def _read_choice() -> int:
    """Ask for 1, 2, 3, or 4 and return the matching option index."""
    while True:
        raw = input("Your answer (1-4): ").strip()
        if raw in {"1", "2", "3", "4"}:
            return int(raw) - 1
        print("Type a number from 1 to 4.")


def play(n: int = 5, difficulty: str = "medium", kind: str | None = None) -> float:
    """Ask ``n`` questions in the terminal and save the session.

    Parameters
    ----------
    n : int, optional
        How many questions to ask.
    difficulty : str, optional
        ``easy``, ``medium``, or ``hard``.
    kind : str, optional
        One question kind. When omitted, the kinds rotate.

    Returns
    -------
    float
        The session score from 0 to 100.
    """
    if n < 1:
        raise RuntimeError("A session needs at least one question")
    countries = build_country_table().countries
    scores = country_similarity(countries).scores
    kinds = [kind] if kind else list(KINDS)
    session_id = datetime.now().isoformat(timespec="seconds")
    records = []
    outcomes: list[tuple[bool, float]] = []

    for number in range(1, n + 1):
        question_kind = kinds[(number - 1) % len(kinds)]
        codes = list(countries_for(countries, question_kind))
        if not codes:
            raise RuntimeError(f"No countries available for {question_kind}")
        country_code = choice(codes)
        question = generate_question(
            countries,
            scores,
            country_code,
            question_kind,
            difficulty,
        )
        print(f"\nQuestion {number}")
        print(question.prompt)
        for index, option in enumerate(question.options, start=1):
            print(f"  {index}. {option}")
        choice = _read_choice()
        correct = question.options[choice] == question.answer
        outcomes.append((correct, question.realized_difficulty))
        earned, maximum = question_points(correct, question.realized_difficulty)
        if correct:
            print("Correct.")
        else:
            print(f"The answer was {question.answer}.")
        records.append(
            {
                "session_id": session_id,
                "kind": question.kind,
                "country_code": question.country_code,
                "difficulty": question.difficulty,
                "realized_difficulty": question.realized_difficulty,
                "correct": correct,
                "earned": earned,
                "maximum": maximum,
            }
        )

    score = session_score(outcomes)
    append_attempt(pd.DataFrame(records, columns=COLUMNS))
    print(f"\nScore: {score:.1f}")
    return score


def main() -> None:
    """Print the worked example. Pass ``play`` to answer questions."""
    if len(sys.argv) > 1 and sys.argv[1] == "play":
        play()
        return
    missed_hard = session_score([(True, 0.2), (False, 0.8), (True, 0.5)])
    missed_easy = session_score([(False, 0.2), (True, 0.8), (True, 0.5)])
    print(f"Miss the hard question: {missed_hard:.1f}")
    print(f"Miss the easy question instead: {missed_easy:.1f}")


if __name__ == "__main__":
    main()
