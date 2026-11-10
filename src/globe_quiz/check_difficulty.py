"""Check that a hard draw is more similar than an easy draw.

For every country the same random start is used twice: once in the easy
band and once in the hard band. The hard mean should be higher. France is
printed in full so the two sets of wrong answers can be compared by eye.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.distractors import sample_distractors
from globe_quiz.similarity import country_similarity


def compare_difficulties(scores: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Compare the easy and hard mean similarity for every country.

    Parameters
    ----------
    scores : pandas.DataFrame
        Square similarity matrix labeled by ``cca3``.
    seed : int, optional
        Random start shared by the easy draw and the hard draw.

    Returns
    -------
    pandas.DataFrame
        Columns ``cca3``, ``easy``, and ``hard``.
    """
    rows = []
    for code in scores.index:
        easy = sample_distractors(scores, code, "easy", rng=np.random.default_rng(seed))
        hard = sample_distractors(scores, code, "hard", rng=np.random.default_rng(seed))
        rows.append(
            {
                "cca3": code,
                "easy": easy.realized_difficulty,
                "hard": hard.realized_difficulty,
            }
        )
    return pd.DataFrame(rows)


def _print_draw(names: pd.Series, scores: pd.DataFrame, country_code: str, difficulty: str) -> None:
    """Print the correct country and the three wrong answers."""
    draw = sample_distractors(
        scores,
        country_code,
        difficulty,
        rng=np.random.default_rng(0),
    )
    wrong = ", ".join(
        f"{names.loc[code]} ({similarity:.2f})"
        for code, similarity in zip(draw.codes, draw.similarities)
    )
    print(f"{difficulty}: {names.loc[country_code]} | {wrong}")
    print(f"  mean similarity {draw.realized_difficulty:.3f}")


def main() -> None:
    """Print France, then how many countries have a higher hard score."""
    countries = build_country_table().countries
    scores = country_similarity(countries).scores
    names = countries.set_index("cca3")["name"]
    _print_draw(names, scores, "FRA", "easy")
    _print_draw(names, scores, "FRA", "hard")
    comparison = compare_difficulties(scores)
    higher = int((comparison["hard"] > comparison["easy"]).sum())
    print(f"{higher} of {len(comparison)} countries have a harder draw that is more similar")


if __name__ == "__main__":
    main()
