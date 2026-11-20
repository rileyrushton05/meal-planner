# 0004: Ingredient lines read by rules, not a language model

## Context

Pasting a recipe means turning "2 x 400 g cans diced tomatoes" into 800 g of
Diced Tomatoes, consistently, so the grocery list can add it to the same
item from another meal. A language model reads lines like that well.

## Decision

A rule-based parser (`app/parsing.py`): numbers, fractions and ranges,
units spelled the app's one way, multipliers, preparation set aside, and
names matched literally against the catalogue's names and aliases. It
reports a confidence and a reason for anything doubtful, and the person
checks every line before anything is saved.

## Alternatives rejected

- **A hosted model.** A per-request cost a stranger could run up, different
  answers to the same line, latency on a free tier, and a prompt that a
  recipe page could talk into anything.

## Consequences

- Free, deterministic, and testable as a table: `tests/test_parsing.py`
  holds over a hundred example lines, and adding a failing example is a
  one-line change. Rules were broken on purpose one at a time to check the
  table catches each.
- Linear in the line's length, so bounded input means bounded work.
- Lines it does not understand are shown as written, flagged, rather than
  guessed at. Catalogue gaps are found by running real lines through it.
