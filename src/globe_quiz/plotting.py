"""Draw summary charts of the quiz data.

One chart counts the countries kept in each region. Another counts empty
World Bank rows for each indicator. The third compares the similarity of
easy, medium, and hard wrong answers.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.distractors import sample_distractors
from globe_quiz.io_countries import project_root
from globe_quiz.io_worldbank import INDICATORS, load_indicators
from globe_quiz.similarity import country_similarity

INDICATOR_ORDER = list(INDICATORS.values())


def figures_dir(root: Path | None = None) -> Path:
    """Return the ``figures`` directory, creating it when it is missing."""
    directory = (root or project_root()) / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def plot_countries_by_region(countries: pd.DataFrame, path: Path) -> Path:
    """Save a bar chart of how many kept countries are in each region.

    Parameters
    ----------
    countries : pandas.DataFrame
        Joined country table. Only countries that stayed in the quiz.
    path : pathlib.Path
        Where to write the PNG file.

    Returns
    -------
    pathlib.Path
        The file that was written.
    """
    counts = countries.groupby("region").size().sort_values()
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.barh(counts.index, counts.to_numpy())
    axis.set_xlabel("Countries kept in the quiz")
    axis.set_title("Countries by region")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return path


def plot_missing_indicators(observations: pd.DataFrame, path: Path) -> Path:
    """Save a bar chart of empty values for each indicator.

    Parameters
    ----------
    observations : pandas.DataFrame
        Long World Bank table, one row per country or region and year.
    path : pathlib.Path
        Where to write the PNG file.

    Returns
    -------
    pathlib.Path
        The file that was written.
    """
    missing = observations["value"].isna().groupby(observations["indicator"]).sum()
    missing = missing.reindex(INDICATOR_ORDER)
    rows_per_indicator = int(observations.groupby("indicator").size().max())
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.bar(missing.index, missing.to_numpy())
    axis.set_ylabel("Empty rows")
    axis.set_title(f"Empty World Bank values out of {rows_per_indicator} rows")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return path


def difficulty_similarities(scores: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Draw one easy, medium, and hard trio for every country.

    Parameters
    ----------
    scores : pandas.DataFrame
        Square similarity matrix labeled by ``cca3``.
    seed : int, optional
        Random start shared by the three draws, as in the difficulty check.

    Returns
    -------
    pandas.DataFrame
        Columns ``difficulty`` and ``similarity``. One row per country and band.
    """
    rows = []
    for code in scores.index:
        for difficulty in ("easy", "medium", "hard"):
            draw = sample_distractors(scores, code, difficulty, rng=np.random.default_rng(seed))
            rows.append({"difficulty": difficulty, "similarity": draw.realized_difficulty})
    return pd.DataFrame(rows)


def plot_difficulty_bands(scores: pd.DataFrame, path: Path) -> Path:
    """Save a box plot of wrong-answer similarity for the three bands.

    Parameters
    ----------
    scores : pandas.DataFrame
        Square similarity matrix labeled by ``cca3``.
    path : pathlib.Path
        Where to write the PNG file.

    Returns
    -------
    pathlib.Path
        The file that was written.
    """
    table = difficulty_similarities(scores)
    groups = [
        table.loc[table["difficulty"] == name, "similarity"].to_numpy()
        for name in ("easy", "medium", "hard")
    ]
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.boxplot(groups)
    axis.set_xticks([1, 2, 3], ["easy", "medium", "hard"])
    axis.set_ylabel("Mean similarity of the three wrong answers")
    axis.set_title("Harder questions use more similar wrong answers")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return path


def main() -> None:
    """Write the charts under ``figures/``."""
    directory = figures_dir()
    countries = build_country_table().countries
    observations = load_indicators()
    scores = country_similarity(countries).scores
    region_path = plot_countries_by_region(countries, directory / "countries_by_region.png")
    missing_path = plot_missing_indicators(observations, directory / "missing_indicators.png")
    difficulty_path = plot_difficulty_bands(scores, directory / "difficulty_bands.png")
    print(region_path)
    print(missing_path)
    print(difficulty_path)


if __name__ == "__main__":
    main()
