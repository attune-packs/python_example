#!/usr/bin/env python3
"""
Flaky Fail Action - Python Example Pack

A Python action that sleeps for a configurable duration and then randomly fails
with a configurable probability. Useful for testing error handling, retry logic,
workflow failure paths, and with_items concurrency behavior.

Actions receive parameters as JSON on stdin and write results to stdout.
"""

import json
import random
import sys
import time


def main():
    # Read parameters from stdin (JSON format)
    params = json.loads(sys.stdin.readline())
    failure_probability = float(params.get("failure_probability", 0.1))
    sleep_seconds = float(params.get("sleep_seconds", 0))

    # Clamp to valid ranges
    failure_probability = max(0.0, min(1.0, failure_probability))
    sleep_seconds = max(0.0, sleep_seconds)

    # Sleep for the configured duration
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    roll = random.random()
    failed = roll < failure_probability

    if failed:
        print(
            json.dumps(
                {
                    "error": "Random failure triggered",
                    "failure_probability": failure_probability,
                    "sleep_seconds": sleep_seconds,
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
                "sleep_seconds": sleep_seconds,
                "roll": round(roll, 6),
            }
        )
    )


if __name__ == "__main__":
    main()
