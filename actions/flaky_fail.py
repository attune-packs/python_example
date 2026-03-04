#!/usr/bin/env python3
"""
Flaky Fail Action - Python Example Pack

A Python action that randomly fails with a configurable probability.
Useful for testing error handling, retry logic, and workflow failure paths.

Actions receive parameters as JSON on stdin and write results to stdout.
"""

import json
import random
import sys


def main():
    # Read parameters from stdin (JSON format)
    params = json.loads(sys.stdin.readline())
    failure_probability = float(params.get("failure_probability", 0.1))

    # Clamp to valid range
    failure_probability = max(0.0, min(1.0, failure_probability))

    roll = random.random()
    failed = roll < failure_probability

    if failed:
        print(
            json.dumps(
                {
                    "error": "Random failure triggered",
                    "failure_probability": failure_probability,
                    "roll": round(roll, 6),
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        json.dumps(
            {
                "message": "Success! Did not fail this time.",
                "failure_probability": failure_probability,
                "roll": round(roll, 6),
            }
        )
    )


if __name__ == "__main__":
    main()
