#!/usr/bin/env python3
"""
Read Counter Action - Python Example Pack

Consumes a counter value (typically from the counter sensor trigger payload)
and returns a formatted message containing the counter value.

Parameters are delivered via stdin as JSON from the Python wrapper.
"""

import json
import sys


def run(counter=0, rule_ref="unknown", **kwargs):
    """Return a message containing the counter value.

    Args:
        counter: The counter value from the trigger payload.
        rule_ref: The rule reference that produced this counter.
        **kwargs: Additional parameters (ignored).

    Returns:
        dict with a formatted message and the raw counter value.
    """
    return {
        "message": f"Counter value is {counter} (from rule: {rule_ref})",
        "counter": counter,
        "rule_ref": rule_ref,
    }


def main():
    """Entry point when run directly (without the Python wrapper)."""
    try:
        content = sys.stdin.read().strip()
        if content:
            parts = content.split("---ATTUNE_PARAMS_END---")
            params = json.loads(parts[0].strip()) if parts[0].strip() else {}
        else:
            params = {}
    except (json.JSONDecodeError, IndexError):
        params = {}

    result = run(**params)
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
