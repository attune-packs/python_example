#!/usr/bin/env python3
"""
Simulate Work Action - Python Example Pack

Simulates a unit of work that takes a configurable amount of time.
Returns structured JSON output with timing information and an optional
payload. Useful for testing workflows, the timeline DAG visualizer,
and execution monitoring.

Parameters:
  duration_seconds  - How long to simulate work (float, default: 1.0)
  label             - A label for this work unit (string, default: "work")
  fail              - Whether to simulate a failure (bool, default: false)
  fail_after        - If failing, fail after this many seconds (float, default: 0)
  output_data       - Arbitrary JSON data to include in the result (default: null)

Output (JSON):
  label             - The label that was passed in
  duration_seconds  - Actual elapsed time
  requested_seconds - The requested duration
  output_data       - The pass-through data (if any)
  success           - Always true on success (failures exit non-zero)
"""

import time
import sys

import attune


def main(
    duration_seconds: float = 1.0,
    label: str = "work",
    fail: bool = False,
    fail_after: float = 0,
    output_data=None,
):

    # Clamp duration to a reasonable range
    duration_seconds = max(0.0, min(duration_seconds, 300.0))

    print(
        f"[simulate_work] Starting '{label}' for {duration_seconds}s", file=sys.stderr
    )

    start = time.time()

    if fail and fail_after > 0:
        # Sleep for fail_after seconds then crash
        time.sleep(min(fail_after, duration_seconds))
        elapsed = round(time.time() - start, 3)
        raise RuntimeError(
            f"Simulated failure in '{label}' after {elapsed}s (elapsed={elapsed})"
        )

    if fail:
        # Immediate failure
        raise RuntimeError(f"Simulated immediate failure in '{label}'")

    # Simulate work with periodic progress to stderr
    remaining = duration_seconds
    while remaining > 0:
        chunk = min(remaining, 1.0)
        time.sleep(chunk)
        remaining -= chunk
        elapsed = round(time.time() - start, 3)
        pct = min(100.0, round((elapsed / max(duration_seconds, 0.001)) * 100, 1))
        print(
            f"[simulate_work] '{label}' progress: {pct}% ({elapsed}s)", file=sys.stderr
        )

    elapsed = round(time.time() - start, 3)

    result = {
        "label": label,
        "duration_seconds": elapsed,
        "requested_seconds": duration_seconds,
        "success": True,
    }
    if output_data is not None:
        result["output_data"] = output_data

    print(f"[simulate_work] '{label}' completed in {elapsed}s", file=sys.stderr)
    return result


if __name__ == "__main__":
    attune.run_action(main)
