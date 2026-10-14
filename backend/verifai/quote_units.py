"""Unpromoted exact-text segmentation candidate; no entailment decisions."""


def exact_units(block):
    """Keep punctuation inside balanced parentheses with its surrounding text.

    This preserves exact contiguous source slices. It neither repairs already
    truncated source context nor asserts that an emitted unit supports a claim.
    Unclosed parentheses conservatively keep the remaining block together.
    """
    units = []
    start = 0
    depth = 0
    for index, character in enumerate(block):
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        if (
            character in ".!?"
            and depth == 0
            and index + 1 < len(block)
            and block[index + 1].isspace()
        ):
            unit = block[start : index + 1].strip()
            if unit:
                units.append(unit)
            start = index + 1
    tail = block[start:].strip()
    if tail:
        units.append(tail)
    return units
