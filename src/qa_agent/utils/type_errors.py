"""Utility module with mypy type errors for QA scenario 02."""
from __future__ import annotations


def process(count: int) -> int:
    return count * 2


def add_optional(x: int | None, y: int) -> int:
    return x + y


def returns_wrong_type(flag: bool) -> int:
    if flag:
        return 42
    return "not an int"


def caller_passes_wrong_type() -> None:
    result = process("hello")
    print(result)
