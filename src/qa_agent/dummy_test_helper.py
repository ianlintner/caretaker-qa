"""Test helper module to validate caretaker v0.28.0 auto-fix loop.

This file is intentionally written with several lint, format, and
correctness issues so caretaker's review→auto-fix→re-review pipeline
can be exercised end-to-end on a real PR.

Safe to delete once the validation PR closes.
"""

import os  # unused import — should be removed by ruff
import sys


def add_numbers(a, b ):
    """Add two numbers."""
    result=a+b   # PEP 8: missing spaces around operator
    return result


def divide_safely(numerator, denominator):
    """Divide two numbers but doesn't actually guard against zero."""
    return numerator / denominator   # bug: divides by zero without check


def get_first_item(items):
    """Return the first item — but doesn't handle empty list."""
    return items[0]   # bug: IndexError on empty list


def parse_count(value: str) -> int:
    """Parse an int — uses bare except, hides everything."""
    try:
        return int(value)
    except:   # bare except — should be `except ValueError`
        return 0


def UnusedFunction():   # naming convention violation: should be snake_case
    pass
