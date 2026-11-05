"""Join countries to the latest World Bank value of each indicator.

The year is chosen separately for every country and every indicator. A
country stays in the quiz table only when all four indicators have a value.
Rows that are dropped are counted in the report returned with the table.
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from globe_quiz.io_countries import load_countries
from globe_quiz.io_worldbank import INDICATORS, load_indicators

# The countries file labels Kosovo with the user-assigned code UNK.
# The World Bank publishes the same place as XKX.
CODE_ALIASES = {"UNK": "XKX"}

INDICATOR_NAMES = list(INDICATORS.values())
YEAR_COLUMNS = [f"{name}_year" for name in INDICATOR_NAMES]


class CountryTable(NamedTuple):
    """Joined country table, the drop counts, and the dropped country rows."""

    countries: pd.DataFrame
    report: pd.DataFrame
    dropped: pd.DataFrame


def latest_indicator_values(observations: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest non-null year for each country code and indicator.

    Parameters
    ----------
    observations : pandas.DataFrame
        Long World Bank table from ``load_indicators``. Rows without a
        country code or a value are ignored, so income groups do not appear.

    Returns
    -------
    pandas.DataFrame
        One row per country code, with a value column and a ``_year`` column
        for each indicator.

    Raises
    ------
    RuntimeError
        No observation has both a country code and a value.
    """
    valued = observations.dropna(subset=["country_code", "value"]).copy()
    if valued.empty:
        raise RuntimeError("World Bank table has no indicator values")

    valued = valued.sort_values(["country_code", "indicator", "year"])
    latest = valued.groupby(["country_code", "indicator"], as_index=False).tail(1)
    values = latest.pivot(index="country_code", columns="indicator", values="value")
    years = latest.pivot(index="country_code", columns="indicator", values="year")
    values = values.reindex(columns=INDICATOR_NAMES)
    years = years.reindex(columns=INDICATOR_NAMES)
    years.columns = YEAR_COLUMNS
    wide = values.join(years)
    wide.index.name = "wb_code"
    return wide.reset_index()


def _blank_code(codes: pd.Series) -> pd.Series:
    """Return True where a country code is missing or blank."""
    text = codes.fillna("").astype(str).str.strip()
    return text.eq("") | text.eq("None")


def _missing_indicators(row: pd.Series) -> str:
    """Name the indicators that have no value on this row."""
    missing = [name for name in INDICATOR_NAMES if pd.isna(row[name])]
    return "missing:" + ",".join(missing)


def _filter_borders(countries: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop border codes that are not in the kept table.

    Neighbour questions can only offer countries that remain after the join.
    Kosovo keeps the code UNK, which is the code its neighbours already use.

    Parameters
    ----------
    countries : pandas.DataFrame
        Kept countries, one row per ``cca3``.

    Returns
    -------
    tuple
        The same table with borders replaced, and how many links were removed.
    """
    kept_codes = set(countries["cca3"])
    before = int(countries["borders"].map(len).sum())
    countries = countries.copy()
    countries["borders"] = countries["borders"].map(
        lambda codes: [code for code in codes if code in kept_codes]
    )
    after = int(countries["borders"].map(len).sum())
    return countries, before - after


def build_country_table(
    countries: pd.DataFrame | None = None,
    observations: pd.DataFrame | None = None,
) -> CountryTable:
    """Join country attributes to the latest World Bank figures.

    The join key is ``cca3``, except Kosovo: the countries file calls it
    ``UNK`` and the World Bank calls it ``XKX``. The stored country code
    stays ``UNK``, because neighbouring countries use that code in their
    border lists.

    A country is dropped when it has no code, when the World Bank has no
    series for it, or when at least one of the four indicators is missing.
    The report counts each of those cases. Every kept indicator also stores
    the year of the value, and those years are allowed to differ.

    Parameters
    ----------
    countries : pandas.DataFrame, optional
        Table from ``load_countries``. Loaded from disk when omitted.
    observations : pandas.DataFrame, optional
        Table from ``load_indicators``. Loaded from disk when omitted.

    Returns
    -------
    CountryTable
        ``countries`` is one row per kept country. ``report`` has a ``step``
        and a ``count``. ``dropped`` lists the source countries that were
        not kept, with a ``reason``.

    Raises
    ------
    RuntimeError
        The drop counts do not add up to the number of source countries.
    """
    if countries is None:
        countries = load_countries()
    if observations is None:
        observations = load_indicators()

    source_count = len(countries)
    blank_world_bank_rows = int(observations["country_code"].isna().sum())
    wide = latest_indicator_values(observations)

    usable = countries.loc[~_blank_code(countries["cca3"])].copy()
    dropped_missing_code = source_count - len(usable)
    usable["wb_code"] = usable["cca3"].replace(CODE_ALIASES)

    merged = usable.reset_index(drop=True).merge(wide, how="left", on="wb_code")
    present = merged[INDICATOR_NAMES].notna().any(axis=1)
    complete = merged[INDICATOR_NAMES].notna().all(axis=1)
    no_match = ~present
    incomplete = present & ~complete

    dropped_no_match = merged.loc[no_match, ["name", "cca3"]].copy()
    dropped_no_match["reason"] = "no_world_bank_match"
    dropped_incomplete = merged.loc[incomplete, ["name", "cca3"]].copy()
    dropped_incomplete["reason"] = merged.loc[incomplete].apply(_missing_indicators, axis=1)
    dropped = pd.concat([dropped_no_match, dropped_incomplete], ignore_index=True)
    dropped = dropped.sort_values(["reason", "name"]).reset_index(drop=True)

    kept = merged.loc[complete].drop(columns=["wb_code"]).copy()
    for column in YEAR_COLUMNS:
        kept[column] = kept[column].astype("Int64")
    value_block = [item for name in INDICATOR_NAMES for item in (name, f"{name}_year")]
    kept = kept[list(usable.columns.drop("wb_code")) + value_block]
    kept, removed_borders = _filter_borders(kept)
    kept = kept.sort_values("name").reset_index(drop=True)

    kept_count = len(kept)
    report = pd.DataFrame(
        [
            ("source_countries", source_count),
            ("dropped_missing_country_code", dropped_missing_code),
            ("world_bank_rows_without_country_code", blank_world_bank_rows),
            ("world_bank_codes_not_used", int(len(set(wide["wb_code"]) - set(usable["wb_code"])))),
            ("dropped_no_world_bank_match", int(no_match.sum())),
            ("dropped_incomplete_indicators", int(incomplete.sum())),
            ("border_links_removed", removed_borders),
            ("kept_countries", kept_count),
        ],
        columns=["step", "count"],
    )
    accounted = dropped_missing_code + int(no_match.sum()) + int(incomplete.sum()) + kept_count
    if accounted != source_count:
        raise RuntimeError(
            f"Drop counts add up to {accounted}, but the source has {source_count} countries"
        )
    return CountryTable(kept, report, dropped)


def main() -> None:
    """Build the joined table and print the drop counts."""
    built = build_country_table()
    print(built.report.to_string(index=False))
    different_year = built.countries["population_year"] != built.countries["gdp_year"]
    print(
        f"{int(different_year.sum())} kept countries use a GDP year "
        "other than their population year"
    )


if __name__ == "__main__":
    main()
