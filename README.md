# Around the Globe

Geography quiz that builds one multiple-choice question at a time. Each question has four answers and one of them is correct. Wrong answers are chosen for a requested difficulty: a harder question uses options that are more similar to the correct one. The score of a session weights every question by how difficult that question actually was.

This is a project for the Python module of *Coding for Data Science and Data Management* (University of Milan, 2026/27).

## Setup

```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on macOS and Linux. Then:

```bash
pip install -r requirements.txt
```

The libraries are NumPy, pandas, Matplotlib, and Jupyter. Downloads use the Python standard library.

From the project folder, put the package on the path once per terminal:

```powershell
$env:PYTHONPATH = "src"
```

```bash
export PYTHONPATH=src
```

## How to run

| Command | What it does |
| --- | --- |
| `python -m globe_quiz.io_countries` | Download the country file and print the table size |
| `python -m globe_quiz.io_worldbank` | Download four indicators and print the row counts |
| `python -m globe_quiz.cleaning` | Join the two tables and print how many countries were dropped |
| `python -m globe_quiz.similarity` | Print the similarity of France to a few other countries |
| `python -m globe_quiz.distractors` | Print one easy and one hard set of wrong answers for France |
| `python -m globe_quiz.quiz` | Print a flag, population, and neighbour question about France |
| `python -m globe_quiz.scoring` | Print the worked score example |
| `python -m globe_quiz.scoring play` | Ask five questions in the terminal and save the session |
| `python -m globe_quiz.scoring history` | Print one score per saved session |
| `python -m globe_quiz.check_difficulty` | Check that hard wrong answers are more similar than easy ones |
| `python -m globe_quiz.plotting` | Write the charts in `figures/` |
| `jupyter notebook notebooks/exploration.ipynb` | Open the presentation notebook |

The notebook calls this package. It does not repeat the loading, the similarity formula, the question rules, or the score.

## Data

- [World countries](https://github.com/mledoze/countries) — names, capitals, regions, languages, currencies, borders, coordinates, and flag emoji. The file has no flag images.
- [World Bank indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) — population (`SP.POP.TOTL`), GDP (`NY.GDP.MKTP.CD`), GDP per capita (`NY.GDP.PCAP.CD`), and life expectancy (`SP.DYN.LE00.IN`).

The country file is saved in `data/raw/`. The indicators are requested for 2000–2026, page by page, and saved in `data/cache/worldbank/`. A failed page is requested again. The API returns only years it has published. Later runs read the saved files.

These paths are not committed: `data/raw/`, `data/cache/`, and `data/results/`.

## Joined table

Countries are joined to the indicators on `cca3`. Kosovo is the exception: the country file calls it `UNK`, and the World Bank calls it `XKX`. The stored code stays `UNK`, because neighbouring countries use that code in their border lists.

For each indicator, the value is the latest year that is not empty. Population and GDP of the same country may come from different years. A country is dropped when the World Bank has no series for it, or when one of the four indicators is missing. Income groups and World Bank regions are not countries, so they stay out of the table. The cleaning command prints the counts.

## Similarity

Every pair of kept countries gets a score from 0 to 1. A country compared with itself scores 1. The score is a weighted sum of five parts:

| Part | Weight | What is close |
| --- | ---: | --- |
| Geography | 0.25 | Great-circle distance, with a fifth of this part reserved for a shared subregion |
| Economy | 0.25 | Ratio of GDP per capita |
| Demography | 0.20 | Life expectancy and population, in equal parts |
| Language | 0.15 | Share of official language names (Jaccard) |
| Currency | 0.15 | At least one currency name in common |

Distance uses the haversine formula and an Earth radius of 6371 km. A gap of 4000 km, or of 10 years of life expectancy, brings that piece down to about 0.37. Micronesia has no currency in the source file, so it shares a currency with nobody. It still scores 1 against itself.

## Questions

Each question has one prompt, four different options, and one correct answer. Three wrong answers are drawn from a similarity band:

- easy: the least similar 30 percent
- medium: percentiles 40 to 70
- hard: the most similar 20 percent, from percentile 80 upward

Countries that would also be a correct answer are left out before the draw. If fewer than three countries remain, easy extends toward more similar countries, hard extends toward less similar ones, and medium extends both ways, five percentiles at a time. The recorded difficulty is the average similarity of the three answers that were drawn, not the name of the band.

The option shown for a country is its first capital, first official language, or first currency. Any other capital, language, or currency of the country being asked about is also treated as correct, so it is not offered as a mistake. South Africa is asked with Pretoria. Bloemfontein and Cape Town are not offered as wrong answers. Macau has no capital, and Micronesia has no currency, so those questions are skipped.

Flag questions show the flag emoji and ask for the country name. Population questions show a rounded figure: billions and millions for large countries, thousands for smaller ones. A hard population question stays near the true figure, within a factor of two when three such countries exist. That factor grows for countries the size of China or India. An easy question uses a figure at least ten times larger or smaller. Neighbour questions use land borders. The correct option is one neighbour, and the other three countries do not share a land border with the subject. Countries with no land border, including islands and Australia, are not asked.

## Score

A correct answer scores `1 + difficulty`. A wrong answer scores 0. The maximum for a question is also `1 + difficulty`, so a harder question is worth more. The session score is `100 * earned / maximum`.

Three questions with difficulties 0.2 (correct), 0.8 (wrong), and 0.5 (correct) score `100 * 2.7 / 4.5 = 60`. If the easy question is the one that is missed, the score is `100 * 3.3 / 4.5 = 73.3`. A completely correct session scores 100.

`play` appends one row per answer to `data/results/attempts.csv`. `history` reads that file and writes `figures/score_history.png`, with one bar per session, after at least one quiz has been played.

## Charts

`python -m globe_quiz.plotting` writes three files:

- `figures/countries_by_region.png` — countries kept in the quiz, by region
- `figures/missing_indicators.png` — empty World Bank rows for each indicator
- `figures/difficulty_bands.png` — mean similarity of easy, medium, and hard wrong answers

The difficulty check prints both sets for France and counts how often the hard set is more similar than the easy set.

## Layout

- `src/globe_quiz/` — the package
- `notebooks/exploration.ipynb` — the presentation
- `figures/` — charts written by the commands above
- `requirements.txt` — pinned libraries
