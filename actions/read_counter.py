#!/usr/bin/env python3
"""
Read Counter Action - Python Example Pack

Consumes a counter value (typically from the counter sensor trigger payload)
and returns a formatted message containing the counter value.

Parameters are delivered via stdin as JSON.
"""

import json
import sys


def main():
    # Read parameters from stdin (JSON format)
    params = json.loads(sys.stdin.readline())

    counter = params.get("counter", 0)
    rule_ref = params.get("rule_ref", "unknown")

    result = {
        "message": f"Counter value is {counter} (from rule: {rule_ref})",
        "counter": counter,
        "rule_ref": rule_ref,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
