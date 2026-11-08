"""Draw wrong answers from a difficulty band of the similarity matrix.

Easy answers come from the least similar countries, hard answers from the
most similar ones. The band gets wider when too few countries are allowed
to appear. The difficulty that is kept is the average similarity of the
countries actually drawn, not the name of the requested band.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import NamedTuple

import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.similarity import country_similarity

# Percentile windows of similarity to the correct country. The gaps between
# 30 and 40, and between 70 and 80, keep the three bands from sharing a border.
BANDS = {
    "easy": (0.0, 30.0),
    "medium": (40.0, 70.0),
    "hard": (80.0, 100.0),
}
WIDEN_STEP = 5.0
DEFAULT_DISTRACTORS = 3


class Distractors(NamedTuple):
    """Three wrong answers and the difficulty they actually have.

    ``realized_difficulty`` is the mean similarity of ``codes`` to
    ``correct_code``. ``lower_percentile`` and ``upper_percentile`` are the
    window used after any widening.
    """

    correct_code: str
    codes: tuple[str, ...]
    difficulty: str
    similarities: tuple[float, ...]
    realized_difficulty: float
    lower_percentile: float
    upper_percentile: float

    @property
    def widened(self) -> bool:
        """Return whether the requested band was not wide enough."""
        requested_low, requested_high = BANDS[self.difficulty]
        return (self.lower_percentile, self.upper_percentile) != (requested_low, requested_high)


def _other_countries(scores: pd.DataFrame, correct_code: str) -> pd.Series:
    """Return similarities from one country to every other country."""
    if scores.shape[0] != scores.shape[1] or not scores.index.equals(scores.columns):
        raise RuntimeError("Similarity matrix must be square, with matching labels")
    if correct_code not in scores.index:
        raise RuntimeError(f"Unknown country code: {correct_code}")
    return scores.loc[correct_code].drop(labels=[correct_code])


def _next_window(difficulty: str, low: float, high: float) -> tuple[float, float]:
    """Grow the percentile window by one step, toward countries still outside it."""
    if difficulty == "easy":
        return low, min(100.0, high + WIDEN_STEP)
    if difficulty == "hard":
        return max(0.0, low - WIDEN_STEP), high
    return max(0.0, low - WIDEN_STEP), min(100.0, high + WIDEN_STEP)


def _in_band(values: np.ndarray, low: float, high: float) -> np.ndarray:
    """Mark values that fall between two percentiles of the full list."""
    lower = float(np.percentile(values, low))
    upper = float(np.percentile(values, high))
    return (values >= lower) & (values <= upper)


def sample_distractors(
    scores: pd.DataFrame,
    correct_code: str,
    difficulty: str,
    n: int = DEFAULT_DISTRACTORS,
    excluded: Collection[str] | None = None,
    rng: np.random.Generator | None = None,
) -> Distractors:
    """Pick ``n`` countries inside a difficulty band.

    Percentiles are computed on every other country. ``excluded`` then removes
    countries that would also be a correct answer, for example a second
    capital or a real neighbour. The correct country itself is always removed.
    If the band has fewer than ``n`` countries left, easy grows toward harder
    countries, hard grows toward easier ones, and medium grows both ways.
    Each step is five percentile points.

    Parameters
    ----------
    scores : pandas.DataFrame
        Square similarity matrix labeled by ``cca3``.
    correct_code : str
        Country the question is about.
    difficulty : str
        ``easy``, ``medium``, or ``hard``.
    n : int, optional
        How many wrong answers to draw. A four-choice question uses 3.
    excluded : collection of str, optional
        Country codes that must not be offered.
    rng : numpy.random.Generator, optional
        Random source. A new generator is used when this is omitted.

    Returns
    -------
    Distractors
        The drawn codes, their similarities, and the window that was used.

    Raises
    ------
    RuntimeError
        The difficulty is unknown, the country is missing, or fewer than
        ``n`` countries remain even after the window covers everyone.
    """
    if difficulty not in BANDS:
        known = ", ".join(BANDS)
        raise RuntimeError(f"Unknown difficulty {difficulty}. Known difficulties: {known}")
    if n < 1:
        raise RuntimeError("At least one distractor is required")

    others = _other_countries(scores, correct_code)
    values = others.to_numpy(dtype=float)
    codes = others.index.astype(str).to_numpy()
    banned = {correct_code, *(excluded or ())}
    eligible = np.array([code not in banned for code in codes])

    low, high = BANDS[difficulty]
    while True:
        available = _in_band(values, low, high) & eligible
        if int(available.sum()) >= n:
            break
        new_low, new_high = _next_window(difficulty, low, high)
        if (new_low, new_high) == (low, high):
            raise RuntimeError(
                f"Could not find {n} distractors for {correct_code} at difficulty {difficulty}"
            )
        low, high = new_low, new_high

    generator = rng or np.random.default_rng()
    picked = generator.choice(np.flatnonzero(available), size=n, replace=False)
    chosen_codes = tuple(str(codes[index]) for index in picked)
    chosen_similarities = tuple(float(values[index]) for index in picked)
    return Distractors(
        correct_code=correct_code,
        codes=chosen_codes,
        difficulty=difficulty,
        similarities=chosen_similarities,
        realized_difficulty=float(np.mean(chosen_similarities)),
        lower_percentile=low,
        upper_percentile=high,
    )


def _format_draw(names: pd.Series, draw: Distractors) -> str:
    """Return one readable line for a draw."""
    choices = ", ".join(
        f"{names.loc[code]} ({similarity:.2f})"
        for code, similarity in zip(draw.codes, draw.similarities)
    )
    window = f"{draw.lower_percentile:.0f}-{draw.upper_percentile:.0f}"
    return f"{draw.difficulty} {draw.realized_difficulty:.3f} (percentiles {window}): {choices}"


def main() -> None:
    """Draw an easy and a hard set of wrong answers for France."""
    countries = build_country_table().countries
    scores = country_similarity(countries).scores
    names = countries.set_index("cca3")["name"]
    easy = sample_distractors(scores, "FRA", "easy", rng=np.random.default_rng(0))
    hard = sample_distractors(scores, "FRA", "hard", rng=np.random.default_rng(0))
    print(_format_draw(names, easy))
    print(_format_draw(names, hard))


if __name__ == "__main__":
    main()
