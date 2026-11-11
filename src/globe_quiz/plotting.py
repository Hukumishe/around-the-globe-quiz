"""Draw two summary charts of the quiz data.

One chart counts the countries kept in each region. The other counts empty
World Bank rows for each indicator, before the latest year is chosen.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from globe_quiz.cleaning import build_country_table
from globe_quiz.io_countries import project_root
from globe_quiz.io_worldbank import INDICATORS, load_indicators

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


def main() -> None:
    """Write both charts under ``figures/``."""
    directory = figures_dir()
    countries = build_country_table().countries
    observations = load_indicators()
    region_path = plot_countries_by_region(countries, directory / "countries_by_region.png")
    missing_path = plot_missing_indicators(observations, directory / "missing_indicators.png")
    print(region_path)
    print(missing_path)


if __name__ == "__main__":
    main()
