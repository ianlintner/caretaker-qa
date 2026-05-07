"""Test helper for caretaker v0.29.2 e2e validation. Safe to delete."""

import os  # unused
import sys


def add_numbers(a, b ):
    """Add two numbers."""
    result=a+b
    return result


def divide_safely(numerator, denominator):
    """Divide — bug: no zero check."""
    return numerator / denominator


def parse_count(value: str) -> int:
    """Parse — bug: bare except."""
    try:
        return int(value)
    except:
        return 0
