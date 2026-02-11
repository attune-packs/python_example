#!/usr/bin/env python3
"""
Hello Action - Python Example Pack

A minimal Python action that returns "Hello, Python".
Demonstrates the basic structure of a Python action in Attune.
"""

import json
import sys


def run(**kwargs):
    """Return a simple greeting message."""
    return {"message": "Hello, Python"}


if __name__ == "__main__":
    result = run()
    print(json.dumps({"result": result, "status": "success"}))
    sys.exit(0)
