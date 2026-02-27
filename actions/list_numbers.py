#!/usr/bin/env python3
"""
List Numbers Action - Python Example Pack

Returns a list of sequential integers as JSON.
Result format: {"items": [start, start+1, ..., start+n-1]}

Actions receive parameters as JSON on stdin and write results to stdout.
"""

import json
import sys


def main():
    # Read parameters from stdin (JSON format)
    params = json.loads(sys.stdin.readline())
    n = int(params.get("n", 10))
    start = int(params.get("start", 0))

    result = {"items": list(range(start, n + start))}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
