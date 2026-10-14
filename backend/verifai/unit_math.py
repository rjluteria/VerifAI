"""Exact arithmetic after two reviewers validate a quoted unit definition."""

import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

NUMBER = r"\d{1,12}(?:\.\d{1,12})?"
MASS = r"micrograms?|milligrams?|kilograms?|grams?|mcg|µg|μg|mg|kg|g"
NAME = r"[A-Za-z][A-Za-z0-9 -]{0,60}?"
IU = r"International Units?|IU"
_CLAIM = re.compile(
    rf"(?P<n>{NUMBER})\s+(?P<unit>{MASS})\s+of\s+(?P<subject>{NAME})\s+"
    rf"(?:equals?|is equal to)\s+(?P<iu>{NUMBER})\s+(?:{IU})\s+of\s+"
    rf"(?P<right>{NAME})\.?",
    re.IGNORECASE,
)
_DEFINITION = re.compile(
    rf"(?<![\w.+-])(?P<n>{NUMBER})\s*(?P<unit>{MASS})\s+"
    rf"(?:of\s+)?(?P<subject>{NAME})\s*(?:equals?|is equal to|=)\s*"
    rf"(?P<iu>{NUMBER})\s*(?:{IU})\b(?=$|[.;(\n]|\s+[.;(\n])",
    re.IGNORECASE,
)
_SCALES = {
    "microgram": 1,
    "milligram": 1000,
    "gram": 1000000,
    "kilogram": 1000000000,
    "mcg": 1,
    "µg": 1,
    "μg": 1,
    "mg": 1000,
    "kg": 1000000000,
    "g": 1000000,
}


def mass_scale(unit):
    # Full words tolerate prose capitalization; SI symbols do not.
    word = unit.lower().removesuffix("s")
    return _SCALES.get(word) if word.endswith("gram") else _SCALES.get(unit)


@dataclass(frozen=True)
class UnitPlan:
    reference_claim: str
    definition: str
    expected: Fraction
    asserted: Fraction

    def label(self):
        return "SUPPORTED" if self.expected == self.asserted else "CONTRADICTED"

    def metadata(self):
        return {
            "method": "exact arithmetic from reviewer-validated unit definition",
            "calculated_IU_fraction": f"{self.expected.numerator}/{self.expected.denominator}",
            "asserted_IU_fraction": f"{self.asserted.numerator}/{self.asserted.denominator}",
        }


def plan_conversion(claim, evidence):
    parsed = _CLAIM.fullmatch(claim)
    if not parsed or parsed["subject"] != parsed["right"]:
        return None
    scale = mass_scale(parsed["unit"])
    if scale is None:
        return None
    plans = []
    for definition in _DEFINITION.finditer(evidence):
        if definition["subject"] != parsed["subject"]:
            continue
        base_scale = mass_scale(definition["unit"])
        base = Fraction(Decimal(definition["n"]))
        target = Fraction(Decimal(definition["iu"]))
        if base_scale is None or base <= 0 or target <= 0:
            continue
        expected = Fraction(Decimal(parsed["n"])) * scale / (base * base_scale) * target
        unit = definition["unit"]
        words = {
            "mcg": "micrograms",
            "µg": "micrograms",
            "μg": "micrograms",
            "mg": "milligrams",
            "kg": "kilograms",
            "g": "grams",
        }
        reference = f"{definition['n']} {words.get(unit, unit)} of {definition['subject']} equals {definition['iu']} International Units of {definition['subject']}."
        plans.append(
            UnitPlan(
                reference, definition[0], expected, Fraction(Decimal(parsed["iu"]))
            )
        )
    if not plans or len({plan.expected for plan in plans}) != 1:
        return None
    return plans[0]
