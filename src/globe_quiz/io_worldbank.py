"""Fetch World Bank indicators into a local cache.

The quiz uses four indicators: population, GDP, GDP per capita, and life
expectancy. Each call reads every page for the years 2000–2026 and stores
the observations under ``data/cache/worldbank/``. A later step picks, for
each country, the latest year that has a value. This module keeps every
observation, including World Bank regions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from globe_quiz.io_countries import project_root

WORLD_BANK_API = "https://api.worldbank.org/v2"
START_YEAR = 2000
END_YEAR = 2026
PER_PAGE = 1000
REQUEST_TIMEOUT_SECONDS = 60
DOWNLOAD_ATTEMPTS = 3

INDICATORS = {
    "SP.POP.TOTL": "population",
    "NY.GDP.MKTP.CD": "gdp",
    "NY.GDP.PCAP.CD": "gdp_per_capita",
    "SP.DYN.LE00.IN": "life_expectancy",
}

COLUMNS = [
    "indicator_id",
    "indicator",
    "indicator_label",
    "country_id",
    "country_name",
    "country_code",
    "year",
    "value",
]


def cache_dir(root: Path | None = None) -> Path:
    """Return ``data/cache/worldbank``, creating it when it is missing."""
    directory = (root or project_root()) / "data" / "cache" / "worldbank"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cache_path(indicator_id: str, root: Path | None = None) -> Path:
    """Return the cache file for one indicator."""
    if indicator_id not in INDICATORS:
        known = ", ".join(INDICATORS)
        raise RuntimeError(f"Unknown indicator {indicator_id}. Known indicators: {known}")
    return cache_dir(root) / f"{indicator_id}.json"


def _indicator_url(indicator_id: str, page: int) -> str:
    """Build the URL of one API page."""
    query = urlencode(
        {
            "format": "json",
            "per_page": PER_PAGE,
            "page": page,
            "date": f"{START_YEAR}:{END_YEAR}",
        }
    )
    return f"{WORLD_BANK_API}/country/all/indicator/{indicator_id}?{query}"


def _retryable(exc: HTTPError) -> bool:
    """Return whether an HTTP status is worth another attempt."""
    return exc.code == 429 or exc.code >= 500


def _read_json(url: str, timeout: float, attempts: int = DOWNLOAD_ATTEMPTS) -> list:
    """Download one URL and decode a JSON list.

    Network failures, HTTP 429, and HTTP 5xx are tried again with a pause
    of 1, then 2, then 4 seconds. A rejected request is not tried again.

    Parameters
    ----------
    url : str
        Full request URL.
    timeout : float
        Seconds to wait for each attempt.
    attempts : int, optional
        How many attempts to make.

    Returns
    -------
    list
        Decoded JSON document.

    Raises
    ------
    RuntimeError
        The request failed, or the body is not a JSON list.
    """
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "globe-quiz/0.1"})
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list):
                raise RuntimeError(f"World Bank response is not a list: {url}")
            return payload
        except HTTPError as exc:
            last_error = exc
            if not _retryable(exc) or attempt == attempts:
                raise RuntimeError(f"Could not download {url}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(
                    f"Could not download {url} after {attempts} attempts"
                ) from exc
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"Could not download {url}") from last_error


def _read_page(indicator_id: str, page: int, timeout: float) -> tuple[dict, list]:
    """Return the metadata and observation rows of one API page."""
    payload = _read_json(_indicator_url(indicator_id, page), timeout)
    if len(payload) < 2 or not isinstance(payload[0], dict):
        message = payload[0].get("message") if payload and isinstance(payload[0], dict) else payload
        raise RuntimeError(f"World Bank rejected {indicator_id}: {message}")
    rows = payload[1] if isinstance(payload[1], list) else []
    return payload[0], rows


def _read_cache(path: Path, indicator_id: str) -> dict | None:
    """Return a cache document when it matches the current request."""
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    observations = document.get("observations")
    if (
        document.get("indicator_id") != indicator_id
        or document.get("start_year") != START_YEAR
        or document.get("end_year") != END_YEAR
        or not isinstance(observations, list)
        or document.get("total") != len(observations)
    ):
        return None
    return document


def _write_cache(path: Path, document: dict) -> None:
    """Replace the cache file only after the full document is on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        temporary.write_text(json.dumps(document), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        if temporary.exists():
            temporary.unlink()
        raise RuntimeError(f"Could not write the cache file {path}") from exc


def download_indicator(
    indicator_id: str,
    refresh: bool = False,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> Path:
    """Download every page of one indicator and return the cache path.

    An existing cache is reused when it covers the same indicator and the
    same years, and when it contains the number of rows the API announced.
    Pages are requested ``PER_PAGE`` rows at a time. The file is written
    only after the downloaded count matches that announcement.

    Parameters
    ----------
    indicator_id : str
        World Bank indicator code, one of ``INDICATORS``.
    refresh : bool, optional
        Download again even if a valid cache file exists.
    timeout : float, optional
        Seconds to wait for each page.

    Returns
    -------
    pathlib.Path
        Path of the cache file.

    Raises
    ------
    RuntimeError
        The indicator is unknown, a page failed, or a page was missed.
    """
    path = cache_path(indicator_id)
    if not refresh and _read_cache(path, indicator_id) is not None:
        return path

    first_meta, first_rows = _read_page(indicator_id, page=1, timeout=timeout)
    page_count = int(first_meta["pages"])
    expected = int(first_meta["total"])
    observations = list(first_rows)
    for page in range(2, page_count + 1):
        _, rows = _read_page(indicator_id, page=page, timeout=timeout)
        observations.extend(rows)

    if len(observations) != expected:
        raise RuntimeError(
            f"Expected {expected} observations for {indicator_id}, "
            f"received {len(observations)}"
        )

    _write_cache(
        path,
        {
            "indicator_id": indicator_id,
            "start_year": START_YEAR,
            "end_year": END_YEAR,
            "lastupdated": first_meta.get("lastupdated"),
            "total": expected,
            "observations": observations,
        },
    )
    return path


def _missing(value: object) -> str | None:
    """Return a stripped string, or None when the API sent a blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: object) -> float | None:
    """Return a float, or None when the observation has no number."""
    if value is None or value == "":
        return None
    return float(value)


def parse_observations(indicator_id: str, observations: list) -> pd.DataFrame:
    """Turn raw API observations into one row per country and year.

    ``country_code`` is the ISO3-style code from the API. World Bank regions
    use the same field, so they stay in the table until the country join.
    Income groups such as "High income" have no code. A blank code or a null
    value becomes a missing cell. ``year`` stays an integer.

    Parameters
    ----------
    indicator_id : str
        Indicator that was requested. Every row is labeled with it.
    observations : list
        Observation objects from the API or from the cache.

    Returns
    -------
    pandas.DataFrame
        Columns listed in ``COLUMNS``, sorted by country code and year.

    Raises
    ------
    RuntimeError
        An observation is not an object, or the indicator is unknown.
    """
    if indicator_id not in INDICATORS:
        raise RuntimeError(f"Unknown indicator {indicator_id}")

    rows: list[dict] = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise RuntimeError("World Bank observation is not an object")
        country = observation.get("country") if isinstance(observation.get("country"), dict) else {}
        indicator = observation.get("indicator") if isinstance(observation.get("indicator"), dict) else {}
        year_text = _missing(observation.get("date"))
        rows.append(
            {
                "indicator_id": indicator_id,
                "indicator": INDICATORS[indicator_id],
                "indicator_label": indicator.get("value"),
                "country_id": _missing(country.get("id")),
                "country_name": _missing(country.get("value")),
                "country_code": _missing(observation.get("countryiso3code")),
                "year": int(year_text) if year_text is not None else None,
                "value": _number(observation.get("value")),
            }
        )

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.sort_values(
        ["country_code", "year"],
        na_position="last",
    ).reset_index(drop=True)


def read_indicator(path: Path, indicator_id: str) -> pd.DataFrame:
    """Read one cache file into a table.

    Parameters
    ----------
    path : pathlib.Path
        Cache file written by ``download_indicator``.
    indicator_id : str
        Indicator code expected inside that file.

    Returns
    -------
    pandas.DataFrame
        One row per observation.

    Raises
    ------
    RuntimeError
        The cache is missing or does not match this indicator and year window.
    """
    document = _read_cache(path, indicator_id)
    if document is None:
        raise RuntimeError(f"Indicator cache is missing or out of date: {path}")
    return parse_observations(indicator_id, document["observations"])


def load_indicator(
    indicator_id: str,
    refresh: bool = False,
) -> pd.DataFrame:
    """Return one indicator, downloading it when the cache is absent.

    Parameters
    ----------
    indicator_id : str
        World Bank indicator code, one of ``INDICATORS``.
    refresh : bool, optional
        Ignore a valid cache and download again.

    Returns
    -------
    pandas.DataFrame
        One row per country or region and year.
    """
    path = download_indicator(indicator_id, refresh=refresh)
    return read_indicator(path, indicator_id)


def load_indicators(refresh: bool = False) -> pd.DataFrame:
    """Return population, GDP, GDP per capita, and life expectancy.

    Parameters
    ----------
    refresh : bool, optional
        Download every indicator again.

    Returns
    -------
    pandas.DataFrame
        The four indicator tables stacked in one frame.
    """
    frames = [load_indicator(indicator_id, refresh=refresh) for indicator_id in INDICATORS]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    """Download any missing indicator and print how many rows were stored."""
    frame = load_indicators()
    first = int(frame["year"].min())
    last = int(frame["year"].max())
    print(f"{len(frame)} observations, published years {first}-{last}")
    counts = frame.groupby("indicator", sort=False).size()
    for name, count in counts.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
