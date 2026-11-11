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

The first run asks the World Bank API for 2000–2026, page by page, and saves four files under `data/cache/worldbank/`: population (`SP.POP.TOTL`), GDP (`NY.GDP.MKTP.CD`), GDP per capita (`NY.GDP.PCAP.CD`), and life expectancy (`SP.DYN.LE00.IN`). The API returns only years it has published. Later runs read those files. Each row is one country, region, or income group, one indicator, and one year. A failed page is requested again.

## Joined country table

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.cleaning
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.cleaning
```

Countries are joined to the indicators on `cca3`. Kosovo is the exception: the country file calls it `UNK`, and the World Bank calls it `XKX`. For each indicator, the value is the latest year that is not empty, so population and GDP of the same country may come from different years. A country is dropped when the World Bank has no series for it, or when one of the four indicators is missing. The command prints how many rows were dropped. Income groups and World Bank regions are not countries, so they stay out of the table.

## Country similarity

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.similarity
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.similarity
```

Every pair of kept countries gets a score from 0 to 1. A country compared with itself scores 1. The score is a weighted sum of five parts:

| Part | Weight | What is close |
| --- | ---: | --- |
| Geography | 0.25 | Great-circle distance, with a fifth of this part reserved for a shared subregion |
| Economy | 0.25 | Ratio of GDP per capita |
| Demography | 0.20 | Life expectancy and population, in equal parts |
| Language | 0.15 | Share of official language names (Jaccard) |
| Currency | 0.15 | At least one currency name in common |

Distance uses the haversine formula and an Earth radius of 6371 km. A gap of 4000 km, or of 10 years of life expectancy, brings that piece down to about 0.37. Micronesia has no currency in the source file, so it shares a currency with nobody; it still scores 1 against itself.

## Wrong answers

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.distractors
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.distractors
```

A question offers three wrong answers. Easy answers are drawn from the least similar 30 percent of countries. Medium uses percentiles 40 to 70. Hard uses the most similar 20 percent, from percentile 80 upward. Countries that would also be correct, such as another capital or a real neighbour, can be left out of the draw. If fewer than three countries remain in the band, easy extends toward more similar countries, hard extends toward less similar ones, and medium extends both ways, five percentiles at a time. The recorded difficulty is the average similarity of the three answers that were drawn.

## Questions

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.quiz
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.quiz
```

Three kinds of question use the same shape: one prompt, four different options, and one correct answer. The option shown for a country is its first capital, first official language, or first currency. Any other capital, language, or currency of the country being asked about is also treated as correct, so it is not used as a wrong answer. South Africa is asked with Pretoria, and Bloemfontein and Cape Town are not offered as mistakes. Macau has no capital, and Micronesia has no currency, so those questions are skipped.

Flag questions show the flag emoji from the country file and ask for the country name. The file does not contain flag images. Population questions show a rounded figure: billions and millions for large countries, thousands for smaller ones. A hard population question stays near the true figure, within a factor of two when three such countries exist, and that factor grows for countries the size of China or India. An easy question uses a figure at least ten times larger or smaller. Neighbour questions use land borders. The correct option is one neighbour, and the other three countries do not share a land border with the subject. Countries with no land border, including islands and Australia, are not asked.

## Score

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.scoring
python -m globe_quiz.scoring play
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.scoring
PYTHONPATH=src python -m globe_quiz.scoring play
```

A correct answer scores `1 + difficulty`, where difficulty is the average similarity of the three wrong answers. A wrong answer scores 0. The session score is `100 * earned / maximum`. Missing a hard question therefore costs more than missing an easy one.

Three questions with difficulties 0.2 (correct), 0.8 (wrong), and 0.5 (correct) score `100 * 2.7 / 4.5 = 60`. If the easy question is the one that is missed, the score is `100 * 3.3 / 4.5 = 73.3`. `play` asks five questions in the terminal and appends them to `data/results/attempts.csv`. That file is not committed.

## Difficulty check

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.check_difficulty
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.check_difficulty
```

For each country the command draws three easy wrong answers and three hard ones from the same random start. It prints both sets for France, then counts how often the hard set is more similar to the correct country than the easy set.

## Plots

```bash
# Windows PowerShell
$env:PYTHONPATH = "src"
python -m globe_quiz.plotting
```

```bash
# macOS or Linux
PYTHONPATH=src python -m globe_quiz.plotting
```

The command writes two charts to `figures/`. `countries_by_region.png` counts the countries that remain in the quiz. `missing_indicators.png` counts empty World Bank rows for population, GDP, GDP per capita, and life expectancy. Each indicator has 6916 rows for 2000–2025.
