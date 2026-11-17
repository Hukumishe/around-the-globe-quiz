"""Geography quiz generated from country data and World Bank indicators.

The notebook calls these pieces:

- ``build_country_table`` joins countries to the latest World Bank values.
- ``country_similarity`` scores every pair of countries from 0 to 1.
- ``generate_question`` builds one question with four options.
- ``session_score`` turns answers and difficulties into a score from 0 to 100.
- ``plot_difficulty_bands`` draws the easy, medium, and hard boxes.
"""

__version__ = "0.1.0"
