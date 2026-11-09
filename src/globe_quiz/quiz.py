"""Build one multiple-choice question about a country.

Each question has four options and one correct answer. The three wrong
options are capitals, languages, or currencies of countries drawn from a
difficulty band. An option that would also be correct is not allowed, so a
country that lists several capitals cannot be given one of the others as a
wrong answer.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.distractors import sample_distractors
from globe_quiz.similarity import country_similarity

KINDS = ("capital", "language", "currency")
PROMPTS = {
    "capital": "Which of these is a capital of {name}?",
    "language": "Which of these is an official language of {name}?",
    "currency": "Which of these is a currency of {name}?",
}
MAX_DRAW_ATTEMPTS = 25


class Question(NamedTuple):
    """One four-option question and the difficulty of the wrong answers.

    ``options`` is shuffled. ``answer`` is the text of the correct option.
    ``realized_difficulty`` is the mean similarity of the three countries
    that supplied the wrong answers.
    """

    kind: str
    country_code: str
    prompt: str
    options: tuple[str, ...]
    answer: str
    difficulty: str
    realized_difficulty: float
    distractor_codes: tuple[str, ...]
    widened: bool


def _clean(value: object) -> str | None:
    """Return a stripped string, or None when the cell is empty."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _as_list(values: object) -> list[object]:
    """Return a list cell as a list. Missing cells become empty."""
    if values is None or (isinstance(values, float) and np.isnan(values)):
        return []
    if isinstance(values, str):
        return [values]
    return list(values)


def _names(values: object) -> set[str]:
    """Return the names stored in a list cell."""
    return {text for item in _as_list(values) if (text := _clean(item))}


def _displayed(row: pd.Series, kind: str) -> str | None:
    """Return the answer text this country would contribute for one kind.

    Capitals, languages, and currencies can have several entries. The text
    used in an option is the first one. The rest are still treated as true,
    so they are not offered as wrong answers.
    """
    if kind == "capital":
        return _clean(row["capital"])
    column = "languages" if kind == "language" else "currencies"
    ordered = [text for item in _as_list(row[column]) if (text := _clean(item))]
    return ordered[0] if ordered else None


def _forbidden(row: pd.Series, kind: str) -> set[str]:
    """Return every text that would be a correct answer for this country."""
    if kind == "capital":
        names = _names(row["capitals"])
        displayed = _displayed(row, kind)
        if displayed:
            names.add(displayed)
        return names
    column = "languages" if kind == "language" else "currencies"
    return _names(row[column])


def _require_kind(kind: str) -> None:
    if kind not in KINDS:
        known = ", ".join(KINDS)
        raise RuntimeError(f"Unknown question kind {kind}. Known kinds: {known}")


def countries_for(countries: pd.DataFrame, kind: str) -> pd.Index:
    """Return the country codes that can be the subject of this kind.

    Macau has no capital in the source file, and Micronesia has no currency.
    Neither can be asked that kind of question, and neither can supply that
    kind of wrong answer.

    Parameters
    ----------
    countries : pandas.DataFrame
        Cleaned country table.
    kind : str
        ``capital``, ``language``, or ``currency``.

    Returns
    -------
    pandas.Index
        ``cca3`` codes that have at least one usable answer text.
    """
    _require_kind(kind)
    by_code = countries.set_index("cca3")
    codes = [str(code) for code, row in by_code.iterrows() if _displayed(row, kind)]
    return pd.Index(codes, name="cca3")


def generate_question(
    countries: pd.DataFrame,
    scores: pd.DataFrame,
    country_code: str,
    kind: str,
    difficulty: str,
    rng: np.random.Generator | None = None,
) -> Question:
    """Ask for the capital, an official language, or a currency.

    Wrong answers come from ``sample_distractors``. Countries whose own
    answer text is already a correct answer for the subject are excluded
    before the draw. If two drawn countries would show the same text, the
    later one is dropped and the draw is repeated.

    Parameters
    ----------
    countries : pandas.DataFrame
        Cleaned country table, one row per ``cca3``.
    scores : pandas.DataFrame
        Similarity matrix labeled by ``cca3``.
    country_code : str
        Country the question is about.
    kind : str
        ``capital``, ``language``, or ``currency``.
    difficulty : str
        ``easy``, ``medium``, or ``hard``.
    rng : numpy.random.Generator, optional
        Random source for the draw and for shuffling the options.

    Returns
    -------
    Question
        Prompt, four unique options, and the realized difficulty.

    Raises
    ------
    RuntimeError
        The kind is unknown, the country has no answer of that kind, or
        three different wrong answers cannot be found.
    """
    _require_kind(kind)
    by_code = countries.set_index("cca3")
    if country_code not in by_code.index:
        raise RuntimeError(f"Unknown country code: {country_code}")
    subject = by_code.loc[country_code]
    answer = _displayed(subject, kind)
    if answer is None:
        raise RuntimeError(f"{country_code} has no {kind} to ask about")
    forbidden = _forbidden(subject, kind)

    excluded: set[str] = set()
    for code, row in by_code.iterrows():
        text = _displayed(row, kind)
        if text is None or text in forbidden:
            excluded.add(str(code))

    generator = rng or np.random.default_rng()
    draw = None
    texts: list[str] = []
    for _ in range(MAX_DRAW_ATTEMPTS):
        draw = sample_distractors(
            scores,
            country_code,
            difficulty,
            excluded=excluded,
            rng=generator,
        )
        texts = [_displayed(by_code.loc[code], kind) for code in draw.codes]
        if any(text is None or text in forbidden for text in texts):
            raise RuntimeError(f"A distractor for {country_code} repeated a correct {kind}")
        if len(set(texts)) == len(texts):
            break
        seen: set[str] = set()
        for code, text in zip(draw.codes, texts):
            if text in seen:
                excluded.add(code)
            else:
                seen.add(text)
    else:
        raise RuntimeError(
            f"Could not find three different {kind} answers for {country_code}"
        )

    options = [answer, *texts]
    order = generator.permutation(len(options))
    shuffled = tuple(options[int(position)] for position in order)
    return Question(
        kind=kind,
        country_code=country_code,
        prompt=PROMPTS[kind].format(name=subject["name"]),
        options=shuffled,
        answer=answer,
        difficulty=difficulty,
        realized_difficulty=draw.realized_difficulty,
        distractor_codes=draw.codes,
        widened=draw.widened,
    )


def _print_question(question: Question) -> None:
    """Print a question and which option is correct."""
    print(question.prompt)
    for option in question.options:
        print(f"  - {option}")
    window = "widened" if question.widened else "not widened"
    print(f"  answer: {question.answer}")
    print(f"  {question.difficulty} {question.realized_difficulty:.3f}, {window}")


def main() -> None:
    """Print one capital, language, and currency question about France."""
    countries = build_country_table().countries
    scores = country_similarity(countries).scores
    generator = np.random.default_rng(0)
    for kind, difficulty in (("capital", "easy"), ("language", "hard"), ("currency", "hard")):
        question = generate_question(
            countries,
            scores,
            "FRA",
            kind,
            difficulty,
            rng=generator,
        )
        _print_question(question)


if __name__ == "__main__":
    main()
