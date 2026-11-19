"""Reading ingredient lines (app/parsing.py).

The table is the specification: one line per example, as a person might
type or paste it, with what it should read as. A line the parser gets wrong
is added here first, failing, and then fixed.
"""

from __future__ import annotations

import time

import pytest

from app.parsing import (
    NOT_KNOWN,
    Confidence,
    canonical_unit,
    parse_line,
    parse_lines,
)

# (line, qty, unit, name). A name that is a catalogue item is spelled as the
# catalogue spells it; anything else keeps the line's own words.
LINES: list[tuple[str, float | None, str, str]] = [
    # Metric, with and without a space, in every spelling.
    ("500g beef mince", 500, "g", "Beef Mince"),
    ("500 g beef mince", 500, "g", "Beef Mince"),
    ("1.5kg potatoes", 1.5, "kg", "Potatoes"),
    ("1 kilo chicken thighs", 1, "kg", "Chicken Thigh"),
    ("250 grams cherry tomatoes", 250, "g", "Cherry Tomatoes"),
    ("250ml cream", 250, "ml", "Cream"),
    ("1 litre milk", 1, "L", "Milk"),
    ("2 L chicken stock", 2, "L", "Chicken Stock"),
    ("750 millilitres vegetable stock", 750, "ml", "Vegetable Stock"),
    # Counts.
    ("2 onions", 2, "", "Onion"),
    ("1 onion", 1, "", "Onion"),
    ("3 eggs", 3, "", "Eggs"),
    ("12 taco shells", 12, "", "Taco Shells"),
    # Fractions, mixed numbers and decimals.
    ("1/2 cup rice", 0.5, "cups", "Rice"),
    ("½ cup rice", 0.5, "cups", "Rice"),
    ("1½ cups plain flour", 1.5, "cups", "Flour"),
    ("1 ½ cups plain flour", 1.5, "cups", "Flour"),
    ("1 1/2 cups milk", 1.5, "cups", "Milk"),
    ("¼ tsp salt", 0.25, "tsp", "Salt"),
    ("0.5 kg rump steak", 0.5, "kg", "Rump Steak"),
    (".5 L milk", 0.5, "L", "Milk"),
    # Spoons and cups.
    ("2 tbsp soy sauce", 2, "tbsp", "Soy Sauce"),
    ("2 Tbsp. olive oil", 2, "tbsp", "Olive Oil"),
    ("1 tablespoon honey", 1, "tbsp", "Honey"),
    ("3 teaspoons curry paste", 3, "tsp", "Curry Paste"),
    ("1 cup of arborio rice", 1, "cups", "Arborio Rice"),
    # Amounts in words.
    ("a pinch of salt", 1, "pinches", "Salt"),
    ("Pinch of salt", 1, "pinches", "Salt"),
    ("an onion", 1, "", "Onion"),
    ("two carrots", 2, "", "Carrots"),
    ("half a cup of milk", 0.5, "cups", "Milk"),
    ("a dozen eggs", 12, "", "Eggs"),
    ("2 dozen eggs", 24, "", "Eggs"),
    ("a couple of tomatoes", 2, "", "Tomato"),
    ("a handful of bean sprouts", 1, "handfuls", "Bean Sprouts"),
    # Ranges: the larger, since that is what to buy.
    ("2-3 garlic cloves", 3, "cloves", "Garlic"),
    ("2\u20133 tomatoes", 3, "", "Tomato"),  # an en dash
    ("1 to 2 tbsp honey", 2, "tbsp", "Honey"),
    ("1 or 2 capsicums", 2, "", "Capsicum"),
    # Pack sizes multiply; the container says how it comes.
    ("1 x 400 g can chopped tomatoes", 400, "g", "Diced Tomatoes"),
    ("2 x 400g cans of tomatoes", 800, "g", "Diced Tomatoes"),
    ("2 \u00d7 400 g tins kidney beans", 800, "g", "Kidney Beans"),  # a times sign
    ("2 (400 g) cans chopped tomatoes", 800, "g", "Diced Tomatoes"),
    ("400g can diced tomatoes", 400, "g", "Diced Tomatoes"),
    ("1 tin tomatoes", 1, "cans", "Diced Tomatoes"),
    ("2 cans chickpeas", 2, "cans", "Chickpeas"),
    ("1 jar pesto", 1, "jars", "Basil Pesto"),
    ("1 packet tortillas", 1, "packets", "Tortillas"),
    ("425 g tin tuna in springwater", 425, "g", "Tuna"),
    # An alternative measure in brackets is the same amount.
    ("250 g (9 oz) cherry tomatoes", 250, "g", "Cherry Tomatoes"),
    ("1 cup (250 ml) milk", 1, "cups", "Milk"),
    # Counted units, at the front or the end of the name.
    ("2 cloves garlic", 2, "cloves", "Garlic"),
    ("1 clove garlic, crushed", 1, "cloves", "Garlic"),
    ("3 garlic cloves", 3, "cloves", "Garlic"),
    ("4 slices bread", 4, "slices", "Bread"),
    ("4 cheese slices", 4, "slices", "Cheese"),
    ("3 rashers bacon", 3, "rashers", "Bacon"),
    ("2 celery sticks", 2, "sticks", "Celery"),
    ("2 fish sticks", 2, "", "Fish sticks"),
    # Describing words are set aside to find the item.
    ("2 large brown onions", 2, "", "Onion"),
    ("1 small red onion, finely diced", 1, "", "Red Onion"),
    ("3 large eggs", 3, "", "Eggs"),
    ("6 free-range eggs", 6, "", "Eggs"),
    ("50 g freshly grated parmesan", 50, "g", "Parmesan"),
    ("500 g lean beef mince", 500, "g", "Beef Mince"),
    ("2 tbsp extra virgin olive oil", 2, "tbsp", "Olive Oil"),
    ("200 g frozen peas", 200, "g", "Frozen Peas"),
    # Imperial, kept as written.
    ("1 lb beef mince", 1, "lb", "Beef Mince"),
    ("8 oz cheddar", 8, "oz", "Cheese"),
    ("4 fl oz cream", 4, "fl oz", "Cream"),
    # The amount at the end, as in a shopping list.
    ("Beef mince 500g", 500, "g", "Beef Mince"),
    ("Eggs x 6", 6, "", "Eggs"),
    ("Milk - 2 L", 2, "L", "Milk"),
    ("Chicken thighs 1kg", 1, "kg", "Chicken Thigh"),
    ("Eggs (6)", 6, "", "Eggs"),
    # Pasted list markers.
    ("- 2 onions", 2, "", "Onion"),
    ("• 500g beef mince", 500, "g", "Beef Mince"),
    ("* 1 cup rice", 1, "cups", "Rice"),
    # Juice and zest.
    ("Juice of 1 lemon", 1, "", "Lemon"),
    ("zest of 2 limes", 2, "", "Limes"),
    # Not in the catalogue: the line's own words, capitalised.
    ("2 tsp smoked paprika", 2, "tsp", "Smoked paprika"),
    ("1 bunch coriander", 1, "bunches", "Coriander"),
    ("3 sprigs thyme", 3, "sprigs", "Thyme"),
    # As recipe sites write them (found importing real pages, 2026-11-19).
    # Notes in nested brackets, some starting with a stray comma:
    ("2 garlic cloves (, minced)", 2, "cloves", "Garlic"),
    ("1 onion (, diced (white or brown))", 1, "", "Onion"),
    ("2 tsp sugar (, if needed (Note 3))", 2, "tsp", "Sugar"),
    ("1 cup red wine ((or beef stock))", 1, "cups", "Red wine"),
    ("Grated parmesan (and parsley (optional))", None, "", "Parmesan"),
    # Two measures of one amount: the metric one.
    ("1 lb / 500g beef mince", 500, "g", "Beef Mince"),
    ("400 g / 14 oz spaghetti", 400, "g", "Pasta"),
    ("800g / 28 oz can crushed tomatoes", 800, "g", "Diced Tomatoes"),
    ("800g / 28 oz can crushed tomato", 800, "g", "Diced Tomatoes"),
    ("1 can whole peeled tomatoes", 1, "cans", "Diced Tomatoes"),
    ("2 cups / 500 ml milk", 500, "ml", "Milk"),
    # Preparation after the name, with no comma before it.
    ("2 carrots peeled and finely chopped", 2, "", "Carrots"),
    ("3 garlic cloves finely chopped", 3, "cloves", "Garlic"),
    ("250 g cherry tomatoes sliced in half", 250, "g", "Cherry Tomatoes"),
    ("1 red chilli deseeded and sliced (optional)", 1, "", "Red chilli"),
    ("2 eggs beaten", 2, "", "Eggs"),
    ("1 tbsp sun dried tomatoes", 1, "tbsp", "Sun dried tomatoes"),
    # A count of cans of a size, with no "x".
    ("1 15oz. can cannellini beans, drained", 15, "oz", "Cannellini beans"),
    ("2 400 g tins chickpeas", 800, "g", "Chickpeas"),
    # Footnote marks and prices are not part of the name.
    ("2 cups vegetable stock*", 2, "cups", "Vegetable Stock"),
    ("1 cup ditalini (uncooked)** ($0.39)", 1, "cups", "Pasta"),
    # No amount.
    ("Salt and pepper, to taste", None, "", "Salt and pepper"),
    ("Salt to taste", None, "", "Salt"),
    ("a few sprigs of thyme", None, "sprigs", "Thyme"),
    ("some olive oil", None, "", "Olive Oil"),
    ("Fresh basil", None, "", "Fresh basil"),
]


@pytest.mark.parametrize(
    ("line", "qty", "unit", "name"), LINES, ids=[row[0] for row in LINES]
)
def test_each_line_reads_as_a_person_means_it(line, qty, unit, name) -> None:
    parsed = parse_line(line)

    assert (parsed.qty, parsed.unit, parsed.name) == (
        pytest.approx(qty) if qty else qty,
        unit,
        name,
    )


def test_the_table_is_long_enough_to_mean_something() -> None:
    assert len(LINES) >= 60


# --- Preparation ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "prep"),
    [
        ("1 clove garlic, crushed", "crushed"),
        ("1 kg potatoes, peeled and chopped", "peeled and chopped"),
        ("1 small red onion, finely diced", "small, finely diced"),
        ("1 onion (finely chopped)", "finely chopped"),
        ("50 g freshly grated parmesan", "freshly grated"),
        ("Salt and pepper, to taste", "to taste"),
        ("Coriander to serve", "to serve"),
        ("Juice of 1 lemon", "juice"),
        ("a few sprigs of thyme", "a few"),
        ("2 onions", ""),
        ("2 garlic cloves (, minced)", "minced"),
        ("1 onion (, diced (white or brown))", "diced (white or brown)"),
        ("2 tsp sugar (, if needed (Note 3))", "if needed"),
        ("2 carrots peeled and finely chopped", "peeled and finely chopped"),
        ("1 cup ditalini (uncooked)** ($0.39)", "uncooked"),
        ("1 can beans, drained and rinsed ($0.89)", "drained and rinsed"),
        (
            "1 red chilli deseeded and sliced (optional)",
            "deseeded and sliced, optional",
        ),
    ],
)
def test_preparation_is_kept_apart_from_the_name(line, prep) -> None:
    assert parse_line(line).prep == prep


# --- Confidence -----------------------------------------------------------------


def test_an_amount_and_a_catalogue_item_is_certain() -> None:
    parsed = parse_line("500g beef mince")

    assert parsed.confidence is Confidence.HIGH
    assert parsed.catalog_item == "Beef Mince"
    assert parsed.warnings == ()


def test_a_name_outside_the_catalogue_wants_a_look() -> None:
    parsed = parse_line("2 tsp smoked paprika")

    assert parsed.confidence is Confidence.MEDIUM
    assert parsed.catalog_item is None
    assert parsed.warnings == (NOT_KNOWN,)


def test_a_range_says_which_end_it_took() -> None:
    parsed = parse_line("2-3 garlic cloves")

    assert parsed.confidence is Confidence.MEDIUM
    assert parsed.warnings == ("Read 2 to 3 as 3.",)


def test_no_amount_is_unsure_and_says_so() -> None:
    parsed = parse_line("Salt to taste")

    assert parsed.confidence is Confidence.LOW
    assert parsed.qty is None
    assert parsed.warnings[0] == "No amount found."


def test_an_alternative_measure_is_not_a_doubt() -> None:
    assert parse_line("250 g (9 oz) cherry tomatoes").confidence is Confidence.HIGH


@pytest.mark.parametrize("line", ["0 eggs", "1/0 cup rice", "", "   ", "(", "x"])
def test_nonsense_is_read_without_failing(line) -> None:
    parsed = parse_line(line)

    assert parsed.qty is None or parsed.qty > 0
    assert parsed.confidence is Confidence.LOW


# --- The catalogue ---------------------------------------------------------------


def test_matching_uses_the_catalogue_it_is_given() -> None:
    catalogue = {"zucchini": "Zucchini", "courgette": "Zucchini"}

    assert parse_line("2 courgettes", catalogue).catalog_item is None
    assert parse_line("2 courgette", catalogue).catalog_item == "Zucchini"
    assert parse_line("2 onions", catalogue).catalog_item is None


def test_the_line_itself_is_kept_tidy_for_the_preview() -> None:
    assert parse_line("  2   onions ").text == "2 onions"


# --- A pasted list ---------------------------------------------------------------


def test_a_pasted_list_skips_blank_lines_and_headings() -> None:
    pasted = """
    For the sauce:
    2 tbsp soy sauce

    1 tbsp honey
    Ingredients:
    """

    parsed = parse_lines(pasted)

    assert [line.name for line in parsed] == ["Soy Sauce", "Honey"]


# --- A unit typed on its own -------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "spelled"),
    [
        ("clove", "cloves"),
        ("Cloves", "cloves"),
        ("Tbsp.", "tbsp"),
        ("tablespoons", "tbsp"),
        ("grams", "g"),
        ("l", "L"),
        ("litre", "L"),
        ("tin", "cans"),
        ("cup", "cups"),
        ("fl. oz", "fl oz"),
        (" g ", "g"),
        ("", ""),
        ("Heaped Spoon", "Heaped Spoon"),  # not known: kept as written
    ],
)
def test_a_typed_unit_is_spelled_as_the_app_spells_it(typed, spelled) -> None:
    assert canonical_unit(typed) == spelled


# --- Bounded work ------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "1 " * 5_000,
        "(" * 10_000,
        "1 x " * 2_500,
        "1-" * 5_000,
        "a" * 10_000,
        "1/2 " * 2_500,
        ", " * 5_000,
        "large " * 1_700,
    ],
    ids=[
        "numbers",
        "brackets",
        "packs",
        "ranges",
        "one word",
        "fractions",
        "commas",
        "describing words",
    ],
)
def test_a_hostile_line_is_still_read_quickly(line) -> None:
    """The API caps a line at 200 characters; this is fifty times that, so
    a pattern that backtracks would show as seconds, not milliseconds."""
    start = time.perf_counter()
    parse_line(line)

    assert time.perf_counter() - start < 0.25
