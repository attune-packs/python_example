#!/usr/bin/env python3
"""
HTTP Example Action - Python Example Pack

Demonstrates using Python's standard library to make an HTTP call to example.com.
Bootstraps parameters/output via attune.run_action.
"""

import urllib.request

import attune


def main(url: str = "https://example.com"):

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as response:
        text = response.read().decode("utf-8")
        status_code = response.status
        final_url = response.url

    result = {
        "status_code": status_code,
        "url": final_url,
        "content_length": len(text),
        "snippet": text[:500],
        "success": 200 <= status_code < 400,
    }
    return result


if __name__ == "__main__":
    attune.run_action(main)
