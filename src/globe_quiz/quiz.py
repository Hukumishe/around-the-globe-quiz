"""Build one multiple-choice question about a country.

Each question has four options and one correct answer. Wrong options are
drawn from a difficulty band. An option that would also be correct is not
allowed. Neighbour questions use land borders only, and population questions
keep the wrong figures in a range that matches the requested difficulty.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.distractors import sample_distractors
from globe_quiz.similarity import country_similarity

KINDS = ("capital", "language", "currency", "flag", "population", "neighbour")
PROMPTS = {
    "capital": "Which of these is a capital of {name}?",
    "language": "Which of these is an official language of {name}?",
    "currency": "Which of these is a currency of {name}?",
    "flag": "Which country has this flag: {flag}?",
    "population": "Which of these is the population of {name}?",
    "neighbour": "Which of these countries borders {name}?",
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


def format_population(population: float) -> str:
    """Round a population to a short label.

    Billions use one decimal. Millions use one decimal below 100 million and
    none above that. Thousands use one decimal below 100 thousand.

    Parameters
    ----------
    population : float
        Number of people.

    Returns
    -------
    str
        Label such as ``68.7 million`` or ``9.5 thousand``.
    """
    number = float(population)
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f} billion"
    if number >= 100_000_000:
        return f"{number / 1_000_000:.0f} million"
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f} million"
    if number >= 100_000:
        return f"{number / 1_000:.0f} thousand"
    if number >= 1_000:
        return f"{number / 1_000:.1f} thousand"
    return f"{number:.0f}"


def _displayed(row: pd.Series, kind: str) -> str | None:
    """Return the answer text this country would contribute for one kind.

    Capitals, languages, and currencies can have several entries. The text
    used in an option is the first one. The rest are still treated as true,
    so they are not offered as wrong answers. Flag and neighbour options are
    country names. A population option is the rounded label.
    """
    if kind == "capital":
        return _clean(row["capital"])
    if kind in ("language", "currency"):
        column = "languages" if kind == "language" else "currencies"
        ordered = [text for item in _as_list(row[column]) if (text := _clean(item))]
        return ordered[0] if ordered else None
    if kind in ("flag", "neighbour"):
        return _clean(row["name"])
    if kind == "population":
        value = row["population"]
        if value is None or (isinstance(value, float) and np.isnan(value)) or float(value) <= 0:
            return None
        return format_population(float(value))
    raise RuntimeError(f"Unknown question kind {kind}")


def _forbidden(by_code: pd.DataFrame, country_code: str, kind: str) -> set[str]:
    """Return every text that would be a correct answer for this country."""
    row = by_code.loc[country_code]
    if kind == "capital":
        names = _names(row["capitals"])
        displayed = _displayed(row, kind)
        if displayed:
            names.add(displayed)
        return names
    if kind == "language":
        return _names(row["languages"])
    if kind == "currency":
        return _names(row["currencies"])
    if kind == "population":
        text = _displayed(row, kind)
        return {text} if text else set()
    if kind == "flag":
        flag = _clean(row["flag"])
        return {
            name
            for _, other in by_code.iterrows()
            if _clean(other["flag"]) == flag and (name := _clean(other["name"]))
        }
    raise RuntimeError(f"Unknown question kind {kind}")


def _population_allowed(by_code: pd.DataFrame, country_code: str, difficulty: str) -> set[str]:
    """Return countries whose population is in the requested range.

    Hard starts within a factor of two and the factor grows until three
    different labels exist. Medium starts between two and five times, and
    its outer edge grows. Easy starts at least ten times larger or smaller,
    and that requirement shrinks only when three labels are not available.
    China and India need a wider hard window than France does.
    """
    population = by_code["population"].astype(float)
    subject = float(population.loc[country_code])
    ratios = (population / subject).drop(labels=[country_code])
    answer = _displayed(by_code.loc[country_code], "population")

    def enough(mask: pd.Series) -> bool:
        labels = {
            text
            for code in ratios.index[mask.to_numpy()]
            if (text := _displayed(by_code.loc[code], "population")) and text != answer
        }
        return len(labels) >= 3

    if difficulty == "hard":
        factor = 2.0
        while factor <= 30:
            mask = (ratios >= 1 / factor) & (ratios <= factor)
            if enough(mask):
                return set(ratios.index[mask.to_numpy()].astype(str))
            factor += 1
    elif difficulty == "easy":
        factor = 10.0
        while factor >= 2:
            mask = (ratios >= factor) | (ratios <= 1 / factor)
            if enough(mask):
                return set(ratios.index[mask.to_numpy()].astype(str))
            factor -= 1
    else:
        outer = 5.0
        while outer <= 40:
            mask = ((ratios >= 1 / outer) & (ratios <= outer)) & ((ratios < 0.5) | (ratios > 2))
            if enough(mask):
                return set(ratios.index[mask.to_numpy()].astype(str))
            outer += 1
    return {str(code) for code in ratios.index}


def _require_kind(kind: str) -> None:
    if kind not in KINDS:
        known = ", ".join(KINDS)
        raise RuntimeError(f"Unknown question kind {kind}. Known kinds: {known}")


def countries_for(countries: pd.DataFrame, kind: str) -> pd.Index:
    """Return the country codes that can be the subject of this kind.

    Macau has no capital in the source file, and Micronesia has no currency.
    A neighbour question needs at least one land border. Australia and the
    island countries in this table have none, so they are skipped.

    Parameters
    ----------
    countries : pandas.DataFrame
        Cleaned country table.
    kind : str
        One of ``KINDS``.

    Returns
    -------
    pandas.Index
        ``cca3`` codes that can be asked this kind of question.
    """
    _require_kind(kind)
    by_code = countries.set_index("cca3")
    codes = []
    for code, row in by_code.iterrows():
        if kind == "neighbour":
            allowed = bool(_names(row["borders"]))
        elif kind == "flag":
            allowed = bool(_clean(row["flag"]) and _displayed(row, kind))
        else:
            allowed = bool(_displayed(row, kind))
        if allowed:
            codes.append(str(code))
    return pd.Index(codes, name="cca3")


def _draw_unique(
    scores: pd.DataFrame,
    country_code: str,
    difficulty: str,
    by_code: pd.DataFrame,
    excluded: set[str],
    forbidden: set[str],
    kind: str,
    generator: np.random.Generator,
):
    """Draw three countries whose option texts are different and not correct."""
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
            return draw, texts
        seen: set[str] = set()
        for code, text in zip(draw.codes, texts):
            if text in seen:
                excluded.add(code)
            else:
                seen.add(text)
    raise RuntimeError(f"Could not find three different {kind} answers for {country_code}")


def _make_question(
    kind: str,
    country_code: str,
    subject: pd.Series,
    answer: str,
    texts: list[str],
    draw,
    generator: np.random.Generator,
) -> Question:
    """Shuffle the correct answer among the three wrong ones."""
    options = [answer, *texts]
    order = generator.permutation(len(options))
    shuffled = tuple(options[int(position)] for position in order)
    flag = _clean(subject["flag"]) or ""
    return Question(
        kind=kind,
        country_code=country_code,
        prompt=PROMPTS[kind].format(name=subject["name"], flag=flag),
        options=shuffled,
        answer=answer,
        difficulty=draw.difficulty,
        realized_difficulty=draw.realized_difficulty,
        distractor_codes=draw.codes,
        widened=draw.widened,
    )


def generate_question(
    countries: pd.DataFrame,
    scores: pd.DataFrame,
    country_code: str,
    kind: str,
    difficulty: str,
    rng: np.random.Generator | None = None,
) -> Question:
    """Ask one four-option question about a country.

    Wrong answers come from ``sample_distractors``. Countries whose own
    answer text is already a correct answer for the subject are excluded
    before the draw. If two drawn countries would show the same text, the
    later one is dropped and the draw is repeated.

    A neighbour question picks one land neighbour as the correct option and
    refuses every other neighbour as a wrong option. A country with no land
    border cannot be asked. Population questions also limit how close the
    wrong figures are allowed to be.

    Parameters
    ----------
    countries : pandas.DataFrame
        Cleaned country table, one row per ``cca3``.
    scores : pandas.DataFrame
        Similarity matrix labeled by ``cca3``.
    country_code : str
        Country the question is about.
    kind : str
        One of ``KINDS``.
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
    generator = rng or np.random.default_rng()

    if kind == "neighbour":
        borders = [str(code) for code in _names(subject["borders"])]
        if not borders:
            raise RuntimeError(f"{country_code} has no land neighbours to ask about")
        answer_code = str(generator.choice(borders))
        answer = _displayed(by_code.loc[answer_code], kind)
        if answer is None:
            raise RuntimeError(f"{answer_code} has no name to offer as a neighbour")
        forbidden = {
            name
            for code in borders
            if (name := _displayed(by_code.loc[code], kind))
        }
        excluded = set(borders)
    else:
        answer = _displayed(subject, kind)
        if answer is None:
            raise RuntimeError(f"{country_code} has no {kind} to ask about")
        forbidden = _forbidden(by_code, country_code, kind)
        excluded = set()
        for code, row in by_code.iterrows():
            text = _displayed(row, kind)
            if text is None or text in forbidden:
                excluded.add(str(code))
        if kind == "population":
            allowed = _population_allowed(by_code, country_code, difficulty)
            for code in by_code.index.astype(str):
                if code != country_code and code not in allowed:
                    excluded.add(code)

    draw, texts = _draw_unique(
        scores,
        country_code,
        difficulty,
        by_code,
        excluded,
        forbidden,
        kind,
        generator,
    )
    return _make_question(kind, country_code, subject, answer, texts, draw, generator)


def _print_question(question: Question) -> None:
    """Print a question and which option is correct."""
    print(question.prompt)
    for option in question.options:
        print(f"  - {option}")
    window = "widened" if question.widened else "not widened"
    print(f"  answer: {question.answer}")
    print(f"  {question.difficulty} {question.realized_difficulty:.3f}, {window}")


def main() -> None:
    """Print a flag, population, and neighbour question about France."""
    countries = build_country_table().countries
    scores = country_similarity(countries).scores
    generator = np.random.default_rng(0)
    for kind, difficulty in (("flag", "hard"), ("population", "hard"), ("neighbour", "easy")):
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
