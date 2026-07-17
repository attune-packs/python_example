#!/usr/bin/env python3
"""
Hello Action - Python Example Pack

A minimal Python action that returns "Hello, Python".
Demonstrates SDK-based action bootstrapping with attune.run_action.
"""

import attune


def main(name: str = "Python"):
    return {"message": f"Hello, {name}"}


if __name__ == "__main__":
    attune.run_action(main)
