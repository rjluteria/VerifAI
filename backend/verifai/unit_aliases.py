"""Conservative quote validation candidate, not a factual inference engine."""

import re

_SCALES = {
    "kilogram": 1000000000,
    "gram": 1000000,
    "milligram": 1000,
    "microgram": 1,
    "kg": 1000000000,
    "g": 1000000,
    "mg": 1000,
    "mcg": 1,
    "ug": 1,
    "µg": 1,
    "μg": 1,
}
_ALTERNATIVES = re.compile(
    r"\b(kilograms?|milligrams?|micrograms?|grams?)\s*"
    r"\(\s*((?:kg|mcg|mg|[µμu]g|g)"
    r"(?:\s*(?:or|/)\s*(?:kg|mcg|mg|[µμu]g|g))+?)\s*\)",
    re.IGNORECASE,
)
_CONVERSION = re.compile(
    r"\d+(?:\.\d+)? (?:kilograms?|milligrams?|micrograms?|grams?) of "
    r"(?P<subject>[A-Za-z0-9][A-Za-z0-9 -]{0,60}) "
    r"(?:equals?|is equal to) \d+(?:\.\d+)? "
    r"(?:International Units?|kilograms?|milligrams?|micrograms?|grams?) "
    r"of (?P=subject)\.?",
    re.IGNORECASE,
)


def is_mass_conversion(claim):
    """Bound guard use to one explicit same-substance conversion claim."""
    return _CONVERSION.fullmatch(claim) is not None


def conflicting_mass_aliases(quote):
    """Flag explicit unscaled aliases with unequal mass scales.

    Numeric conversions, corrections, unknown units and other grammatical
    constructions remain outside this guard. Never silently repair a quote.
    """
    for match in _ALTERNATIVES.finditer(quote):
        named = match[1].lower().removesuffix("s")
        aliases = re.split(r"\s*(?:or|/)\s*", match[2].lower())
        if any(_SCALES[alias] != _SCALES[named] for alias in aliases):
            return True
    return False
