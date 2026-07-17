#!/usr/bin/env python3
"""
Read Counter Action - Python Example Pack

Consumes a counter value (typically from the counter sensor trigger payload)
and returns a formatted message containing the counter value.
"""

import attune


def main(counter: int = 0, rule_ref: str = "unknown"):
    return {
        "message": f"Counter value is {counter} (from rule: {rule_ref})",
        "counter": counter,
        "rule_ref": rule_ref,
    }


if __name__ == "__main__":
    attune.run_action(main)
