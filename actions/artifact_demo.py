#!/usr/bin/env python3
"""
Artifact Demo Action - Python Example Pack

Demonstrates creating file and progress artifacts via the Attune API.
Each iteration:
  1. Appends a timestamped log line to a file artifact (via version upload)
  2. Updates a progress artifact by 2%
  3. Sleeps for 0.5 seconds

The action authenticates to the API using the provided credentials (or defaults)
and uses ATTUNE_API_URL / ATTUNE_EXEC_ID environment variables set by the worker.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def api_request(
    base_url, path, method="GET", data=None, token=None, content_type="application/json"
):
    """Make an HTTP request to the Attune API."""
    url = f"{base_url}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if data is not None:
        if content_type == "application/json":
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            body = data if isinstance(data, bytes) else data.encode("utf-8")
            headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"API error {e.code} on {method} {path}: {error_body}", file=sys.stderr)
        raise


def multipart_upload(
    base_url, path, file_bytes, filename, token, content_type="text/plain"
):
    """Upload a file via multipart/form-data."""
    boundary = f"----AttuneArtifact{int(time.time() * 1000)}"
    body_parts = []

    # file field
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    body_parts.append(file_bytes)
    body_parts.append(b"\r\n")

    # content_type field
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="content_type"\r\n\r\n')
    body_parts.append(content_type.encode())
    body_parts.append(b"\r\n")

    # created_by field
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="created_by"\r\n\r\n')
    body_parts.append(b"python_example.artifact_demo")
    body_parts.append(b"\r\n")

    body_parts.append(f"--{boundary}--\r\n".encode())

    full_body = b"".join(body_parts)

    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, data=full_body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Upload error {e.code} on {path}: {error_body}", file=sys.stderr)
        raise


def login(base_url, username, password):
    """Authenticate and return a JWT token."""
    data, _ = api_request(
        base_url,
        "/auth/login",
        method="POST",
        data={
            "username": username,
            "password": password,
        },
    )
    return data["data"]["access_token"]


def create_artifact(
    base_url,
    token,
    ref,
    name,
    artifact_type,
    execution_id,
    content_type=None,
    description=None,
    data=None,
):
    """Create a new artifact and return its ID."""
    payload = {
        "ref": ref,
        "scope": "action",
        "owner": "python_example.artifact_demo",
        "type": artifact_type,
        "retention_policy": "versions",
        "retention_limit": 10,
        "name": name,
        "execution": execution_id,
    }
    if content_type:
        payload["content_type"] = content_type
    if description:
        payload["description"] = description
    if data is not None:
        payload["data"] = data

    resp, _ = api_request(
        base_url, "/api/v1/artifacts", method="POST", data=payload, token=token
    )
    return resp["data"]["id"]


def append_progress(base_url, token, artifact_id, entry):
    """Append an entry to a progress artifact."""
    api_request(
        base_url,
        f"/api/v1/artifacts/{artifact_id}/progress",
        method="POST",
        data={"entry": entry},
        token=token,
    )


def main():
    start_time = time.time()

    try:
        # Read parameters from stdin (JSON format)
        params = json.loads(sys.stdin.readline())
        iterations = params.get("iterations", 50)
        username = params.get("username") or os.environ.get(
            "ATTUNE_USERNAME", "test@attune.local"
        )
        password = params.get("password") or os.environ.get(
            "ATTUNE_PASSWORD", "TestPass123!"
        )

        # Get execution context from environment
        api_url = os.environ.get("ATTUNE_API_URL", "http://localhost:8080")
        exec_id_str = os.environ.get("ATTUNE_EXEC_ID", "")
        execution_id = int(exec_id_str) if exec_id_str else None

        print(
            f"Artifact demo starting: {iterations} iterations, API at {api_url}",
            file=sys.stderr,
        )

        # Authenticate
        token = login(api_url, username, password)
        print("Authenticated successfully", file=sys.stderr)

        # Build unique artifact refs using execution ID to avoid collisions
        ts = int(time.time())
        ref_suffix = f"{execution_id}_{ts}" if execution_id else str(ts)
        file_ref = f"python_example.artifact_demo.log.{ref_suffix}"
        progress_ref = f"python_example.artifact_demo.progress.{ref_suffix}"

        # Create file artifact (file_text type)
        file_artifact_id = create_artifact(
            base_url=api_url,
            token=token,
            ref=file_ref,
            name="Artifact Demo Log",
            artifact_type="file_text",
            execution_id=execution_id,
            content_type="text/plain",
            description=f"Log output from artifact demo ({iterations} iterations)",
        )
        print(
            f"Created file artifact ID={file_artifact_id} ref={file_ref}",
            file=sys.stderr,
        )

        # Create progress artifact
        progress_artifact_id = create_artifact(
            base_url=api_url,
            token=token,
            ref=progress_ref,
            name="Artifact Demo Progress",
            artifact_type="progress",
            execution_id=execution_id,
            description=f"Progress tracker for artifact demo ({iterations} iterations)",
            data=[],  # Initialize with empty array
        )
        print(
            f"Created progress artifact ID={progress_artifact_id} ref={progress_ref}",
            file=sys.stderr,
        )

        # Run iterations
        log_lines = []
        for i in range(iterations):
            iteration = i + 1
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            pct = min(round(iteration * (100.0 / iterations), 1), 100.0)

            # Build log line
            log_line = f"[{now}] Iteration {iteration}/{iterations} — progress {pct}%"
            log_lines.append(log_line)

            print(f"  Iteration {iteration}/{iterations} ({pct}%)", file=sys.stderr)

            # Upload the full log as a new file version
            full_log = "\n".join(log_lines) + "\n"
            multipart_upload(
                base_url=api_url,
                path=f"/api/v1/artifacts/{file_artifact_id}/versions/upload",
                file_bytes=full_log.encode("utf-8"),
                filename="artifact_demo.log",
                token=token,
                content_type="text/plain",
            )

            # Append progress entry
            append_progress(
                api_url,
                token,
                progress_artifact_id,
                {
                    "iteration": iteration,
                    "total": iterations,
                    "percent": pct,
                    "message": f"Completed iteration {iteration}",
                    "timestamp": now,
                },
            )

            # Sleep between iterations
            if iteration < iterations:
                time.sleep(0.5)

        elapsed = round(time.time() - start_time, 3)
        result = {
            "file_artifact_id": file_artifact_id,
            "progress_artifact_id": progress_artifact_id,
            "iterations_completed": iterations,
            "elapsed_seconds": elapsed,
            "success": True,
        }
        print(json.dumps(result))
        print(f"Artifact demo completed in {elapsed}s", file=sys.stderr)
        return 0

    except Exception as e:
        elapsed = round(time.time() - start_time, 3)
        error_result = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(json.dumps(error_result))
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
