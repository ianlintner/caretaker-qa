"""Utility module — intentionally contains ruff violations for QA scenario 01.

Violations planted:
  E501  line too long (>88 chars)
  F401  unused import
  E711  comparison to None with ==
  W291  trailing whitespace
  I001  import order wrong
"""
import os
import sys
import json
from typing import List,Dict

VERY_LONG_CONSTANT = "this line is intentionally way too long and will definitely exceed the eighty-eight character limit that ruff enforces by default in most projects"

unused_var = "this variable is never referenced again and should trigger F841"  

def check_thing(x,y,z):
    if x == None:
        return False
    result:List[Dict] = []
    for i in range(0,10):
        result.append({"key":i,"value":y+z})
    return result


def another_bad_function( a,b ):
    """Docstring."""
    import re   # noqa-F401 style: late import inside function
    d = dict()
    d["key"] = a+b
    return d
