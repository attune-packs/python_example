#!/usr/bin/env python3
"""
HTTP Example Action - Python Example Pack

Demonstrates using the `requests` library to make an HTTP call to example.com.
Receives parameters via stdin JSON (through the Python wrapper).
"""

import requests


def run(url="https://example.com", **kwargs):
    """Fetch a URL and return status and a snippet of the response body."""
    response = requests.get(url, timeout=10)

    return {
        "status_code": response.status_code,
        "url": response.url,
        "content_length": len(response.text),
        "snippet": response.text[:500],
        "success": response.ok,
    }
