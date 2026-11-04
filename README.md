# Around the Globe

Geography quiz that builds one multiple-choice question at a time. Each question has four answers and one of them is correct. Wrong answers are chosen for a requested difficulty: a harder question uses options that are more similar to the correct one. The score of a session weights every question by how difficult that question actually was.

This is a project for the Python module of *Coding for Data Science and Data Management* (University of Milan, 2026/27).

## Data

- [World countries](https://github.com/mledoze/countries) — names, capitals, regions, languages, currencies, borders, coordinates, and flags.
- [World Bank indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) — population, GDP, GDP per capita, and life expectancy.

Downloads use the Python standard library. Saved files stay outside git (`data/raw/`, `data/cache/`).

## Libraries

NumPy, pandas, Matplotlib, and Jupyter.

## Layout

- `src/globe_quiz/` — data loading, quiz generation, scoring, and plots.
- `requirements.txt` — pinned libraries.

A Jupyter notebook will import this package to show the plots and run the quiz.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
jupyter notebook
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## Country table

From the repository root, with the environment activated:

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.io_countries
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.io_countries
```

The first run downloads `data/raw/countries.json`. Later runs read that file. The table has one row per country: name, ISO code, capital, region, subregion, languages, currencies, borders, coordinates, and flag. Countries with several capitals keep the full list; the `capital` column is the first one.

## World Bank indicators

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.io_worldbank
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.io_worldbank
```

The first run asks the World Bank API for 2000–2026, page by page, and saves four files under `data/cache/worldbank/`: population (`SP.POP.TOTL`), GDP (`NY.GDP.MKTP.CD`), GDP per capita (`NY.GDP.PCAP.CD`), and life expectancy (`SP.DYN.LE00.IN`). The API returns only years it has published. Later runs read those files. Each row is one country, region, or income group, one indicator, and one year. A failed page is requested again. The latest non-empty year for each country is chosen in a later step.

The quiz itself is not playable yet.
