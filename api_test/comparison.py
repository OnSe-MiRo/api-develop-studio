from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Difference:
    path: str
    expected: Any
    actual: Any
    reason: str


def compare_json(expected: Any, actual: Any, path: str = "$", *, strict: bool = True) -> list[Difference]:
    """Compare JSON values recursively and return every detected difference.

    Strict mode requires object keys and array ordering/length to match exactly.
    """
    differences: list[Difference] = []
    if type(expected) is not type(actual):
        return [Difference(path, expected, actual, "type mismatch")]

    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(Difference(f"{path}.{key}", expected[key], None, "missing key"))
        if strict:
            for key in sorted(actual_keys - expected_keys):
                differences.append(Difference(f"{path}.{key}", None, actual[key], "unexpected key"))
        for key in sorted(expected_keys & actual_keys):
            differences.extend(compare_json(expected[key], actual[key], f"{path}.{key}", strict=strict))
        return differences

    if isinstance(expected, list):
        if len(actual) < len(expected) or (strict and len(expected) != len(actual)):
            differences.append(Difference(path, len(expected), len(actual), "array length mismatch"))
        for index, (wanted, received) in enumerate(zip(expected, actual)):
            differences.extend(compare_json(wanted, received, f"{path}[{index}]", strict=strict))
        return differences

    if expected != actual:
        differences.append(Difference(path, expected, actual, "value mismatch"))
    return differences
