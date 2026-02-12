#!/usr/bin/env python3
"""
Hello Action - Python Example Pack

A minimal Python action that returns "Hello, Python".
Demonstrates the basic structure of a self-contained action in Attune.

Actions receive parameters as JSON on stdin and write results to stdout.
"""

import json
import sys


def main():
    # Read parameters from stdin (JSON format)
    params = json.loads(sys.stdin.readline())
    name = params.get("name", "Python")

    result = {"message": f"Hello, {name}"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
