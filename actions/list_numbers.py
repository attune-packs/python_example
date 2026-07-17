#!/usr/bin/env python3
"""
List Numbers Action - Python Example Pack

Returns a list of sequential integers as JSON.
Result format: {"items": [start, start+1, ..., start+n-1]}
"""

import attune


def main(n: int = 10, start: int = 0):
    return {"items": list(range(start, n + start))}


if __name__ == "__main__":
    attune.run_action(main)
