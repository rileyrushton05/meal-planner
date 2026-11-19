"""Reading an ingredient line the way a person writes it.

"500g beef mince", "2 onions", "1 x 400 g can chopped tomatoes", "½ cup rice":
each becomes a quantity, a unit, a name and, where the name is one, the
catalogue item it is, with a confidence and any warnings for the preview a
person checks before saving.

Deterministic and server-side, by decision (D10 in the plan): no language
model, so no cost, no key to protect and no abuse surface, and every result
can be explained by a rule here and pinned by a line in tests/test_parsing.py.

What it does, in order:

1. Tidies the line: bullets, unicode fractions (½), dashes, and a
   multiplication sign written for "x".
2. Sets aside preparation: after a comma ("garlic, crushed"), and phrases
   such as "to taste" or "to serve".
3. Reads the amount: a number, fraction, mixed number ("1 1/2"), a word
   ("a", "two", "half a", "a dozen"), or a range ("2-3", taking the larger,
   since that is what to buy); then a unit. A pack size multiplies:
   "1 x 400 g can" and "2 (400 g) cans" are 400 g and 800 g. A measure in
   brackets after another ("250 g (9 oz)") is an alternative and is dropped.
   With no amount at the start, one at the end is read: "Beef mince 500g".
4. Matches the rest to the catalogue: exactly, as the catalogue's own
   linking does, and then without describing words ("2 large brown onions"
   is Onion) or, after a can or tin, as the canned thing ("400 g can
   tomatoes" is Diced Tomatoes). Never by guessing at plurals or typos: a
   spelling worth matching is an alias in app/catalog.csv.

Units come out in the spellings the rest of the app uses: g, kg, ml, L,
tsp, tbsp, and plurals for counted things (cups, cloves, slices), so a
parsed "1 clove garlic" merges with a template's "2 cloves" on the grocery
list. Ounces and pounds are kept as written, not converted.

Callers limit how long a line may be; this module assumes a sensible one.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from functools import cache
from types import MappingProxyType

from app.catalog import catalog_key, load_catalog


class Confidence(StrEnum):
    #: An amount was read, and the name is a catalogue item.
    HIGH = "high"
    #: An amount was read, but something wants a look: the name is not in
    #: the catalogue, or a range or alternative was resolved.
    MEDIUM = "medium"
    #: No amount, or no name, could be read.
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ParsedLine:
    #: The line as given, with its spacing tidied.
    text: str
    #: None when no amount could be read.
    qty: float | None
    #: "" for a plain count ("2 onions").
    unit: str
    #: The catalogue item's name when matched; otherwise the line's own words.
    name: str
    #: How it is prepared or described: "crushed", "large", "to taste".
    prep: str
    #: The catalogue item matched, if any.
    catalog_item: str | None
    confidence: Confidence
    #: Why the confidence is not high, in words for the preview.
    warnings: tuple[str, ...]


# --- Vocabulary ----------------------------------------------------------------

#: Canonical unit -> every spelling of it. Counted things are plural, as the
#: templates write them.
_UNITS: dict[str, tuple[str, ...]] = {
    "mg": ("mg", "milligram", "milligrams", "milligramme", "milligrammes"),
    "g": ("g", "gm", "gms", "gr", "gram", "grams", "gramme", "grammes"),
    "kg": ("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme"),
    "ml": ("ml", "mls", "millilitre", "millilitres", "milliliter", "milliliters"),
    "L": ("l", "ltr", "litre", "litres", "liter", "liters"),
    "tsp": ("tsp", "tsps", "teaspoon", "teaspoons"),
    "tbsp": ("tbsp", "tbsps", "tbs", "tbl", "tablespoon", "tablespoons"),
    "cups": ("cup", "cups"),
    "fl oz": (),  # read by its own pattern: two words
    "oz": ("oz", "ounce", "ounces"),
    "lb": ("lb", "lbs", "pound", "pounds"),
    "cloves": ("clove", "cloves"),
    "slices": ("slice", "slices"),
    "rashers": ("rasher", "rashers"),
    "stalks": ("stalk", "stalks"),
    "sticks": ("stick", "sticks"),
    "sprigs": ("sprig", "sprigs"),
    "pinches": ("pinch", "pinches"),
    "dashes": ("dash", "dashes"),
    "handfuls": ("handful", "handfuls"),
    "bunches": ("bunch", "bunches"),
    "cans": ("can", "cans", "tin", "tins"),
    "jars": ("jar", "jars"),
    "packets": ("packet", "packets", "pack", "packs", "pkt"),
    "bottles": ("bottle", "bottles"),
    "punnets": ("punnet", "punnets"),
    "bags": ("bag", "bags"),
    "tubs": ("tub", "tubs"),
    "cartons": ("carton", "cartons"),
}
_UNIT_OF = {
    spelling: unit for unit, spellings in _UNITS.items() for spelling in spellings
}

#: Units that are a container: after a size ("400 g can") they say how it
#: comes, not how much.
_CONTAINERS = frozenset(
    {"cans", "jars", "packets", "bottles", "punnets", "bags", "tubs", "cartons"}
)

#: Counted units a name may end with: "garlic cloves" is 2 cloves of Garlic.
_TRAILING_UNITS = frozenset({"cloves", "slices", "rashers", "stalks", "sticks"})

#: Units often written with no amount: "Pinch of salt" is one pinch.
_IMPLIED_ONE = frozenset({"pinches", "dashes", "handfuls", "bunches", "sprigs"})

#: Amounts in words, longest first when matched.
_WORD_AMOUNTS: dict[str, Fraction] = {
    "a couple of": Fraction(2),
    "a couple": Fraction(2),
    "a dozen": Fraction(12),
    "one and a half": Fraction(3, 2),
    "half a": Fraction(1, 2),
    "half an": Fraction(1, 2),
    "a half": Fraction(1, 2),
    "a quarter": Fraction(1, 4),
    "a": Fraction(1),
    "an": Fraction(1),
    "half": Fraction(1, 2),
    "quarter": Fraction(1, 4),
    "dozen": Fraction(12),
    **{
        word: Fraction(n)
        for n, word in enumerate(
            [
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
                "ten",
                "eleven",
                "twelve",
            ],
            start=1,
        )
    },
}

#: Vague amounts: not read as a number, so the person is asked.
_VAGUE = re.compile(r"\s*(?:a few|a little|a bit of|some|several)\b", re.IGNORECASE)

#: Words that describe an item without changing what it is. Dropped only to
#: find a catalogue match, and then kept as preparation.
_DESCRIPTORS = frozenset(
    [
        "large",
        "medium",
        "small",
        "big",
        "extra",
        "fresh",
        "freshly",
        "ripe",
        "lean",
        "boneless",
        "skinless",
        "chopped",
        "diced",
        "sliced",
        "minced",
        "grated",
        "crushed",
        "peeled",
        "finely",
        "roughly",
        "thinly",
        "cooked",
        "raw",
        "frozen",
        "dried",
        "organic",
        "free",
        "range",
    ]
)

#: Phrases that are preparation or serving, wherever they appear.
_SERVING = re.compile(
    r"\b(to taste|as needed|as required|to serve|for serving|"
    r"to garnish|for garnish|optional)\b",
    re.IGNORECASE,
)

_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5", "⅙": "1/6",
    "⅚": "5/6", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}  # fmt: skip
_VULGAR = re.compile(rf"(?:(\d)\s*)?([{''.join(_FRACTIONS)}])")

#: Characters written for "/", "-" and "x": fraction slash, en and em dash,
#: minus sign, multiplication sign.
_LOOKALIKES = str.maketrans(
    {"\u2044": "/", "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00d7": "x"}
)
#: List markers: hyphen, bullet, asterisk, and their typographic cousins.
_BULLETS = "-*\u2022\u00b7\u25aa\u25e6\u2023\u2043 "

_NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+"
_NUMBER_AT_START = re.compile(rf"\s*({_NUMBER})")
_WORD_AT_START = re.compile(
    r"\s*("
    + "|".join(re.escape(w) for w in sorted(_WORD_AMOUNTS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
_RANGE = re.compile(r"\s*(?:-|to\b|or\b)\s*", re.IGNORECASE)
_DOZEN = re.compile(r"\s*dozen\b", re.IGNORECASE)
_TIMES = re.compile(r"\s*x\s*", re.IGNORECASE)
_BRACKETS = re.compile(r"\s*\(([^()]*)\)")
_WORD = re.compile(r"\s*([a-z]+)\.?(?![a-z])", re.IGNORECASE)
_FLUID_OUNCE = re.compile(r"\s*fl\.?\s*oz\.?(?![a-z])", re.IGNORECASE)
_OF = re.compile(r"\s*of\b", re.IGNORECASE)
_JUICE_OR_ZEST = re.compile(r"^(juice|zest)\s+(?:of\s+)?(.+)$", re.IGNORECASE)
#: "Beef mince 500g", "Eggs x 6", "Milk - 2 L", "Eggs (6)": the amount last.
_AMOUNT_AT_END = re.compile(
    rf"^(?P<name>.*?[a-z)])\s*(?:[-:]\s*|x\s*|\(\s*)?"
    rf"(?P<amount>(?:{_NUMBER})\s*(?:[a-z]+\.?)?)\s*\)?$",
    re.IGNORECASE,
)


# --- Parsing -------------------------------------------------------------------


def parse_line(text: str, catalogue: Mapping[str, str] | None = None) -> ParsedLine:
    """Read one ingredient line. `catalogue` maps every catalogue spelling
    (as `catalog_key` writes it) to its item's name; by default, the one in
    app/catalog.csv."""
    names = _default_catalogue() if catalogue is None else catalogue
    tidy = " ".join(text.split())
    line = _normalise(tidy)
    warnings: list[str] = []

    line, prep = _set_aside_prep(line)
    juice = _JUICE_OR_ZEST.match(line)
    if juice:
        prep.insert(0, juice.group(1).lower())
        line = juice.group(2)

    amount = _read(line, prep)
    warnings += amount.warnings

    name, brackets = _without_brackets(amount.rest)
    prep += brackets
    name = _without_of(name).strip(" .;-")

    unit = amount.unit
    item, dropped = None, ""
    if not unit:
        # "3 garlic cloves": the unit at the end of the name. Only when what
        # is left is a catalogue item, so "fish sticks" stays as it is.
        head, _, last = name.rpartition(" ")
        trailing = _UNIT_OF.get(last.lower())
        if head and trailing in _TRAILING_UNITS:
            item, dropped = _match(head, names, canned=False)
            if item:
                unit, name = trailing, head
    if item is None:
        canned = "cans" in (amount.unit, amount.container)
        item, dropped = _match(name, names, canned=canned)
    if dropped:
        prep.insert(0, dropped)

    qty = float(amount.qty) if amount.qty is not None else None
    if qty is None:
        warnings.insert(0, "No amount found.")
    if not name:
        warnings.append("No ingredient name found.")
    elif item is None:
        warnings.append("Not in the catalogue.")

    if qty is None or not name:
        confidence = Confidence.LOW
    elif warnings:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.HIGH

    return ParsedLine(
        text=tidy,
        qty=qty,
        unit=unit,
        name=item or _capitalised(name),
        prep=", ".join(part for part in prep if part),
        catalog_item=item,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def parse_lines(
    text: str, catalogue: Mapping[str, str] | None = None
) -> list[ParsedLine]:
    """Read a pasted list, one ingredient a line. Blank lines and headings
    ("For the sauce:") are skipped."""
    return [
        parse_line(line, catalogue)
        for line in text.splitlines()
        if line.strip() and not line.strip().endswith(":")
    ]


# --- Steps -----------------------------------------------------------------------


@dataclass(slots=True)
class _Amount:
    qty: Fraction | None = None
    unit: str = ""
    #: What follows the amount: the name, and anything in brackets.
    rest: str = ""
    #: A container named after a size: "400 g can".
    container: str = ""
    warnings: list[str] = field(default_factory=list)


def _read(line: str, prep: list[str]) -> _Amount:
    """The amount, wherever it is written: at the start, at the end, or not
    at all ("some salt", "pinch of salt")."""
    vague = _VAGUE.match(line)
    if vague:
        prep.insert(0, vague.group(0).strip().lower())
        unit, rest = _take_unit(line[vague.end() :])
        return _Amount(unit=unit, rest=_without_of(rest))
    amount = _read_amount(line)
    if amount.qty is not None:
        return amount
    unit, rest = _take_unit(line)
    if unit in _IMPLIED_ONE:
        return _Amount(qty=Fraction(1), unit=unit, rest=_without_of(rest))
    return _read_amount_at_end(line) or amount


def _without_of(text: str) -> str:
    return _OF.sub("", text, count=1) if _OF.match(text) else text


def _normalise(line: str) -> str:
    line = _VULGAR.sub(_spelled_fraction, line)
    line = unicodedata.normalize("NFKC", line)
    line = line.translate(_LOOKALIKES)
    return line.lstrip(_BULLETS).strip()


def _spelled_fraction(match: re.Match[str]) -> str:
    """ "1½" -> "1 1/2", "½" -> "1/2"."""
    whole, fraction = match[1], _FRACTIONS[match[2]]
    return f"{whole} {fraction}" if whole else fraction


def _set_aside_prep(line: str) -> tuple[str, list[str]]:
    """Split off what follows the first comma outside brackets, and any
    serving phrase."""
    prep: list[str] = []
    depth = 0
    for i, char in enumerate(line):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            prep.append(line[i + 1 :].strip())
            line = line[:i]
            break
    serving = _SERVING.search(line)
    if serving:
        prep.insert(0, line[serving.start() :].strip())
        line = line[: serving.start()]
    return line.strip(), prep


def _take_qty(text: str) -> tuple[Fraction | None, str]:
    number = _NUMBER_AT_START.match(text)
    if number:
        value = _value(number.group(1))
        if value:
            return value, text[number.end() :]
    word = _WORD_AT_START.match(text)
    if word:
        return _WORD_AMOUNTS[word.group(1).lower()], text[word.end() :]
    return None, text


def _value(number: str) -> Fraction | None:
    whole, _, fraction = number.rpartition(" ") if "/" in number else ("", "", number)
    try:
        value = Fraction(fraction) + (int(whole) if whole else 0)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def _take_unit(text: str) -> tuple[str, str]:
    fluid = _FLUID_OUNCE.match(text)
    if fluid:
        return "fl oz", text[fluid.end() :]
    word = _WORD.match(text)
    if word and word.group(1).lower() in _UNIT_OF:
        return _UNIT_OF[word.group(1).lower()], text[word.end() :]
    return "", text


def _measure(text: str) -> tuple[Fraction, str] | None:
    """The whole of `text` as an amount with a unit, such as "400 g"."""
    qty, rest = _take_qty(text)
    if qty is None:
        return None
    unit, rest = _take_unit(rest)
    return (qty, unit) if unit and not rest.strip() else None


def _drop_container(text: str) -> tuple[str, str]:
    unit, rest = _take_unit(text)
    if unit in _CONTAINERS:
        return unit, _without_of(rest)
    return "", text


def _read_amount(line: str) -> _Amount:
    qty, rest = _take_qty(line)
    if qty is None:
        return _Amount(rest=line)
    amount = _Amount(qty=qty)

    end = _RANGE.match(rest)
    if end:
        upper, after = _take_qty(rest[end.end() :])
        if upper is not None:
            larger = max(qty, upper)
            amount.warnings.append(
                f"Read {_show(qty)} to {_show(upper)} as {_show(larger)}."
            )
            qty, rest = larger, after
    dozen = _DOZEN.match(rest)
    if dozen:
        qty, rest = qty * 12, rest[dozen.end() :]

    # A pack size: "1 x 400 g can", or "2 (400 g) cans".
    times = _TIMES.match(rest)
    size = None
    if times:
        size_qty, after = _take_qty(rest[times.end() :])
        if size_qty is not None:
            size_unit, after = _take_unit(after)
            if size_unit:
                size, rest = (size_qty, size_unit), after
    elif bracket := _BRACKETS.match(rest):
        size = _measure(bracket.group(1))
        if size:
            rest = rest[bracket.end() :]
    if size:
        amount.qty, amount.unit = qty * size[0], size[1]
        amount.container, rest = _drop_container(rest)
        amount.rest = _without_alternative(rest, amount)
        return amount

    amount.qty = qty
    amount.unit, rest = _take_unit(rest)
    if amount.unit and amount.unit not in _CONTAINERS:
        amount.container, rest = _drop_container(rest)
    amount.rest = _without_alternative(rest, amount)
    amount.rest = _without_of(amount.rest)
    return amount


def _without_alternative(text: str, amount: _Amount) -> str:
    """Drop "(9 oz)" after "250 g": the same amount, measured another way."""
    bracket = _BRACKETS.match(text)
    if amount.unit and bracket and _measure(bracket.group(1)):
        return text[bracket.end() :]
    return text


def _read_amount_at_end(line: str) -> _Amount | None:
    end = _AMOUNT_AT_END.match(line)
    if not end:
        return None
    amount = _read_amount(end.group("amount"))
    if amount.qty is None or amount.rest.strip():
        return None
    amount.rest = end.group("name")
    return amount


def _without_brackets(text: str) -> tuple[str, list[str]]:
    """The name without bracketed notes, and the notes: "onion (diced)"."""
    notes = [match.group(1).strip() for match in _BRACKETS.finditer(text)]
    return " ".join(_BRACKETS.sub(" ", text).split()), [n for n in notes if n]


def _match(
    name: str, names: Mapping[str, str], *, canned: bool
) -> tuple[str | None, str]:
    """The catalogue item `name` is, and any describing words set aside to
    find it."""
    key = catalog_key(name.replace("-", " "))
    candidates = [f"canned {key}", key] if canned else [key]
    for candidate in candidates:
        if candidate in names:
            return names[candidate], ""
    words = key.split()
    kept = [word for word in words if word not in _DESCRIPTORS]
    if kept and len(kept) < len(words) and " ".join(kept) in names:
        return names[" ".join(kept)], " ".join(w for w in words if w in _DESCRIPTORS)
    return None, ""


@cache
def _default_catalogue() -> Mapping[str, str]:
    return MappingProxyType(
        {key: entry.name for entry in load_catalog() for key in entry.keys}
    )


def _capitalised(name: str) -> str:
    return name[:1].upper() + name[1:]


def _show(qty: Fraction | None) -> str:
    if qty is None:
        return ""
    return str(int(qty)) if qty.denominator == 1 else f"{float(qty):g}"
