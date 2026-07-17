#!/usr/bin/env python3
"""
Flaky Fail Action - Python Example Pack

A Python action that sleeps for a configurable duration and then randomly fails
with a configurable probability. Useful for testing error handling, retry logic,
workflow failure paths, and with_items concurrency behavior.
"""

import random
import time

import attune


def main(failure_probability: float = 0.1, sleep_seconds: float = 0):

    # Clamp to valid ranges
    failure_probability = max(0.0, min(1.0, failure_probability))
    sleep_seconds = max(0.0, sleep_seconds)

    # Sleep for the configured duration
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    roll = random.random()
    failed = roll < failure_probability

    if failed:
        raise RuntimeError(
            "Random failure triggered "
            f"(p={failure_probability}, sleep_seconds={sleep_seconds}, roll={round(roll, 6)})"
        )

    return {
        "message": "Success! Did not fail this time.",
        "failure_probability": failure_probability,
        "sleep_seconds": sleep_seconds,
        "roll": round(roll, 6),
    }


if __name__ == "__main__":
    attune.run_action(main)
