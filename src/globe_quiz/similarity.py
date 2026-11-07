"""Score how similar every pair of countries is.

The quiz uses this score to pick wrong answers. A harder question draws
its wrong answers from countries that score closer to the correct one.
The five parts and their weights are fixed here and in the README.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

from globe_quiz.cleaning import build_country_table

EARTH_RADIUS_KM = 6371.0
DISTANCE_SCALE_KM = 4000.0
LIFE_EXPECTANCY_SCALE_YEARS = 10.0
GEOGRAPHY_DISTANCE_WEIGHT = 0.8
GEOGRAPHY_SUBREGION_WEIGHT = 0.2

# The five weights sum to 1. Geography already includes the subregion flag,
# so a shared subregion does not add anything on top of these weights.
WEIGHTS = {
    "geography": 0.25,
    "economy": 0.25,
    "demography": 0.20,
    "language": 0.15,
    "currency": 0.15,
}

REQUIRED_COLUMNS = [
    "cca3",
    "subregion",
    "languages",
    "currencies",
    "latitude",
    "longitude",
    "population",
    "gdp_per_capita",
    "life_expectancy",
]


class Similarity(NamedTuple):
    """Final pairwise scores and the five parts that produce them.

    ``scores`` and every frame in ``parts`` use ``cca3`` as the index and
    the columns, in the same order. Values lie in ``[0, 1]``.
    """

    scores: pd.DataFrame
    parts: dict[str, pd.DataFrame]


def _require_countries(countries: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the table, or raise when a required field is missing."""
    missing = [column for column in REQUIRED_COLUMNS if column not in countries.columns]
    if missing:
        raise RuntimeError(f"Country table is missing columns: {', '.join(missing)}")
    if countries["cca3"].duplicated().any():
        raise RuntimeError("Country table has duplicate cca3 codes")
    numeric = ["latitude", "longitude", "population", "gdp_per_capita", "life_expectancy"]
    incomplete = countries[numeric].isna().any(axis=1)
    if incomplete.any():
        names = ", ".join(countries.loc[incomplete, "cca3"].astype(str))
        raise RuntimeError(f"Similarity needs complete coordinates and indicators for: {names}")
    if (countries["population"] <= 0).any() or (countries["gdp_per_capita"] <= 0).any():
        raise RuntimeError("Population and GDP per capita must be positive")
    return countries.reset_index(drop=True)


def _labeled(matrix: np.ndarray, codes: pd.Index) -> pd.DataFrame:
    """Wrap a square array with country-code labels."""
    return pd.DataFrame(matrix, index=codes, columns=codes)


def _haversine_km(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    """Return the great-circle distance in kilometres for every pair.

    Parameters
    ----------
    latitude, longitude : numpy.ndarray
        Decimal degrees, one entry per country.

    Returns
    -------
    numpy.ndarray
        Square distance matrix. The diagonal is zero.
    """
    lat = np.radians(latitude.astype(float))
    lon = np.radians(longitude.astype(float))
    latitude_gap = lat[:, None] - lat[None, :]
    longitude_gap = lon[:, None] - lon[None, :]
    haversine = (
        np.sin(latitude_gap / 2.0) ** 2
        + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(longitude_gap / 2.0) ** 2
    )
    haversine = np.clip(haversine, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine))


def _ratio(values: np.ndarray) -> np.ndarray:
    """Return the smaller value divided by the larger one, for every pair.

    ``exp(-|log a - log b|)`` is that ratio. Equal values give 1.
    """
    logged = np.log(values.astype(float))
    return np.exp(-np.abs(logged[:, None] - logged[None, :]))


def _life_expectancy(values: np.ndarray) -> np.ndarray:
    """Score a gap in life expectancy. Ten years gives about 0.37."""
    gap = np.abs(values.astype(float)[:, None] - values.astype(float)[None, :])
    return np.exp(-gap / LIFE_EXPECTANCY_SCALE_YEARS)


def _same_subregion(subregion: pd.Series) -> np.ndarray:
    """Return 1 when two countries share a non-empty subregion.

    A missing subregion does not match any other country. The diagonal is 1.
    """
    labels = subregion.fillna("").astype(str).to_numpy()
    same = labels[:, None] == labels[None, :]
    missing = labels == ""
    same[missing, :] = False
    same[:, missing] = False
    np.fill_diagonal(same, True)
    return same.astype(float)


def _binary_matrix(values: pd.Series) -> np.ndarray:
    """Encode lists of names as a country-by-name matrix of zeros and ones."""
    rows = [list(items) for items in values]
    vocabulary = sorted({name for items in rows for name in items})
    matrix = np.zeros((len(rows), len(vocabulary)), dtype=float)
    if not vocabulary:
        return matrix
    position = {name: index for index, name in enumerate(vocabulary)}
    for row_index, items in enumerate(rows):
        for name in items:
            matrix[row_index, position[name]] = 1.0
    return matrix


def _jaccard(matrix: np.ndarray) -> np.ndarray:
    """Return the Jaccard similarity of every pair of binary rows.

    Two empty rows would have an empty union. That pair is scored 0, except
    the diagonal, which stays 1 because a country matches its own list.
    """
    if matrix.shape[1] == 0:
        scores = np.zeros((matrix.shape[0], matrix.shape[0]), dtype=float)
        np.fill_diagonal(scores, 1.0)
        return scores
    intersection = matrix @ matrix.T
    sizes = matrix.sum(axis=1)
    union = sizes[:, None] + sizes[None, :] - intersection
    scores = np.zeros_like(intersection)
    np.divide(intersection, union, out=scores, where=union > 0)
    np.fill_diagonal(scores, 1.0)
    return scores


def _shared_name(matrix: np.ndarray) -> np.ndarray:
    """Return 1 when two rows share a 1 in the same column.

    The diagonal is 1 even if that country has an empty list. Micronesia
    has no currency in the source file, and it should still match itself.
    """
    if matrix.shape[1] == 0:
        scores = np.zeros((matrix.shape[0], matrix.shape[0]), dtype=float)
    else:
        scores = ((matrix @ matrix.T) > 0).astype(float)
    np.fill_diagonal(scores, 1.0)
    return scores


def country_similarity(countries: pd.DataFrame | None = None) -> Similarity:
    """Score every pair of countries on a scale from 0 to 1.

    The cleaned table from ``build_country_table`` is used when no table is
    passed. Geography combines great-circle distance with a same-subregion
    flag. Economy is the ratio of GDP per capita. Demography gives equal
    weight to life expectancy and population. Language uses the Jaccard
    index of official languages. Currency is 1 when two countries share a
    currency name.

    Parameters
    ----------
    countries : pandas.DataFrame, optional
        One row per country, including coordinates, languages, currencies,
        and the four World Bank indicators.

    Returns
    -------
    Similarity
        ``scores`` is the weighted result. ``parts`` holds the five
        components before weighting.

    Raises
    ------
    RuntimeError
        A required value is missing, a code is duplicated, or the weights
        do not sum to 1.
    """
    if not np.isclose(sum(WEIGHTS.values()), 1.0):
        raise RuntimeError("Similarity weights must sum to 1")
    if countries is None:
        countries = build_country_table().countries
    countries = _require_countries(countries)
    codes = pd.Index(countries["cca3"].astype(str), name="cca3")

    distance = _haversine_km(countries["latitude"].to_numpy(), countries["longitude"].to_numpy())
    geography = (
        GEOGRAPHY_DISTANCE_WEIGHT * np.exp(-distance / DISTANCE_SCALE_KM)
        + GEOGRAPHY_SUBREGION_WEIGHT * _same_subregion(countries["subregion"])
    )
    economy = _ratio(countries["gdp_per_capita"].to_numpy())
    demography = 0.5 * _life_expectancy(countries["life_expectancy"].to_numpy())
    demography += 0.5 * _ratio(countries["population"].to_numpy())
    language = _jaccard(_binary_matrix(countries["languages"]))
    currency = _shared_name(_binary_matrix(countries["currencies"]))

    parts = {
        "geography": geography,
        "economy": economy,
        "demography": demography,
        "language": language,
        "currency": currency,
    }
    scores = np.zeros_like(geography)
    for name, weight in WEIGHTS.items():
        scores = scores + weight * parts[name]
    scores = np.clip(scores, 0.0, 1.0)
    np.fill_diagonal(scores, 1.0)

    if not np.allclose(scores, scores.T):
        raise RuntimeError("Similarity matrix is not symmetric")
    if not np.allclose(np.diag(scores), 1.0):
        raise RuntimeError("A country must have similarity 1 with itself")

    labeled_parts = {name: _labeled(matrix, codes) for name, matrix in parts.items()}
    return Similarity(_labeled(scores, codes), labeled_parts)


def main() -> None:
    """Print the matrix size and a few country pairs."""
    countries = build_country_table().countries
    result = country_similarity(countries)
    names = countries.set_index("cca3")["name"]
    print(f"{len(result.scores)} countries")
    for left, right in (("FRA", "BEL"), ("FRA", "DEU"), ("FRA", "JPN"), ("FRA", "AUS")):
        print(f"{names.loc[left]} - {names.loc[right]}: {result.scores.loc[left, right]:.3f}")


if __name__ == "__main__":
    main()
