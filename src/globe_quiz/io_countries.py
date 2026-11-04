"""Load the World countries dataset into a pandas table.

The source is the ``countries.json`` file from
https://github.com/mledoze/countries. The download uses the Python standard
library and is stored in ``data/raw/``, which git ignores.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

COUNTRIES_URL = (
    "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
)
REQUEST_TIMEOUT_SECONDS = 60

COLUMNS = [
    "name",
    "official_name",
    "cca3",
    "capital",
    "capitals",
    "region",
    "subregion",
    "languages",
    "currencies",
    "borders",
    "latitude",
    "longitude",
    "flag",
]


def project_root() -> Path:
    """Return the repository root, two levels above this file."""
    return Path(__file__).resolve().parents[2]


def raw_data_dir(root: Path | None = None) -> Path:
    """Return ``data/raw``, creating the directory when it is missing."""
    directory = (root or project_root()) / "data" / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def download_countries(
    destination: Path | None = None,
    url: str = COUNTRIES_URL,
    refresh: bool = False,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> Path:
    """Save ``countries.json`` locally and return its path.

    An existing file is reused unless ``refresh`` is true. The new file is
    written beside the destination and replaces it only after the body looks
    like a JSON list, so a failed download does not destroy a good copy.

    Parameters
    ----------
    destination : pathlib.Path, optional
        Target path. Defaults to ``data/raw/countries.json``.
    url : str, optional
        File URL.
    refresh : bool, optional
        Download again even when ``destination`` already exists.
    timeout : float, optional
        Seconds to wait for the server.

    Returns
    -------
    pathlib.Path
        Path of the local JSON file.

    Raises
    ------
    RuntimeError
        The server could not be reached, or the body is not a JSON list.
    """
    path = destination or (raw_data_dir() / "countries.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return path

    request = Request(url, headers={"User-Agent": "globe-quiz/0.1"})
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
        temporary.write_bytes(payload)
        if not payload.lstrip().startswith(b"["):
            raise RuntimeError(f"Download from {url} is not a JSON list")
        temporary.replace(path)
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
        if temporary.exists():
            temporary.unlink()
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Could not download country data from {url}") from exc
    return path


def _names(mapping: dict | None, nested_name: bool = False) -> list[str]:
    """Return the human-readable values of a code-to-name mapping."""
    if not isinstance(mapping, dict):
        return []
    names: list[str] = []
    for value in mapping.values():
        if nested_name:
            if isinstance(value, dict) and value.get("name"):
                names.append(str(value["name"]))
        elif isinstance(value, str) and value:
            names.append(value)
    return names


def _coordinates(values: list | None) -> tuple[float | None, float | None]:
    """Return latitude and longitude, or a pair of missing values."""
    if not isinstance(values, list) or len(values) < 2:
        return None, None
    return float(values[0]), float(values[1])


def parse_countries(payload: list) -> pd.DataFrame:
    """Turn the raw country list into one row per country.

    ``capital`` is the first capital listed in the dataset. ``capitals``
    keeps the whole list, because South Africa and the Caribbean Netherlands
    have more than one and a quiz must not treat another of them as wrong.
    Language and currency entries keep every name. Border codes stay as
    ``cca3`` values. A missing list becomes an empty list, not a missing cell.

    Parameters
    ----------
    payload : list
        Decoded contents of ``countries.json``.

    Returns
    -------
    pandas.DataFrame
        Columns listed in ``COLUMNS``, sorted by common name.

    Raises
    ------
    RuntimeError
        An entry is not an object, or the list is empty.
    """
    if not payload:
        raise RuntimeError("Country file does not contain any countries")

    rows: list[dict] = []
    for country in payload:
        if not isinstance(country, dict):
            raise RuntimeError("Country file contains an entry that is not an object")
        name = country.get("name") if isinstance(country.get("name"), dict) else {}
        capitals = [str(capital) for capital in country.get("capital") or []]
        latitude, longitude = _coordinates(country.get("latlng"))
        rows.append(
            {
                "name": name.get("common"),
                "official_name": name.get("official"),
                "cca3": country.get("cca3"),
                "capital": capitals[0] if capitals else None,
                "capitals": capitals,
                "region": country.get("region") or None,
                "subregion": country.get("subregion") or None,
                "languages": _names(country.get("languages")),
                "currencies": _names(country.get("currencies"), nested_name=True),
                "borders": [str(code) for code in country.get("borders") or []],
                "latitude": latitude,
                "longitude": longitude,
                "flag": country.get("flag") or None,
            }
        )

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame = frame.dropna(subset=["name", "cca3"])
    frame = frame.drop_duplicates(subset=["cca3"])
    return frame.sort_values("name").reset_index(drop=True)


def read_countries(path: Path) -> pd.DataFrame:
    """Read a local ``countries.json`` file into the country table.

    Parameters
    ----------
    path : pathlib.Path
        Existing JSON file.

    Returns
    -------
    pandas.DataFrame
        One row per country.

    Raises
    ------
    RuntimeError
        The file is missing, is not JSON, or does not contain a list.
    """
    if not path.is_file():
        raise RuntimeError(f"Country file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Country file is not valid JSON: {path}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Country file does not contain a list: {path}")
    return parse_countries(payload)


def load_countries(
    path: Path | None = None,
    url: str = COUNTRIES_URL,
    refresh: bool = False,
) -> pd.DataFrame:
    """Download the World countries file if needed and return the table.

    Territories stay in the result. Deciding which rows can appear in a quiz
    is a later cleaning step. The raw file is not committed.

    Parameters
    ----------
    path : pathlib.Path, optional
        Where to read or store the JSON. Defaults to ``data/raw/countries.json``.
    url : str, optional
        Source URL, used when the file is missing or ``refresh`` is true.
    refresh : bool, optional
        Download again even if a local file already exists.

    Returns
    -------
    pandas.DataFrame
        One row per country. See ``parse_countries`` for the column rules.

    Raises
    ------
    RuntimeError
        The download failed, or the file cannot be parsed.
    """
    destination = path or (raw_data_dir() / "countries.json")
    saved = download_countries(destination, url=url, refresh=refresh)
    return read_countries(saved)


def main() -> None:
    """Download the dataset if needed and print a short summary."""
    countries = load_countries()
    missing_capital = int(countries["capital"].isna().sum())
    print(f"{len(countries)} countries, {missing_capital} without a capital")
    print(", ".join(countries.columns))


if __name__ == "__main__":
    main()
