#!/usr/bin/env python3
"""
Artifact Demo Action - Python Example Pack

Demonstrates creating file and progress artifacts via the Attune API.
Each iteration:
  1. Appends a line to an in-memory log
  2. Updates a progress artifact
  3. Sleeps for 0.5 seconds

After all iterations complete, the full log is written directly to the
shared artifact volume as a **single version** of a file artifact with a
stable ref (`python_example.artifact_demo.log`).

File-based artifact flow (single API call):
  1. POST /api/v1/artifacts/ref/{ref}/versions/file — upserts the artifact
     (creating it if it doesn't exist) and allocates a version number,
     returning a relative `file_path`
  2. Write the file to $ATTUNE_ARTIFACTS_DIR/{file_path} on the shared volume

No HTTP upload is needed — the worker and action process share an artifact
volume, so the action writes directly to disk.

The progress artifact is still per-execution (ephemeral status indicator).

Parameters:
  iterations  - Number of iterations to run (default: 50)
  visibility  - Artifact visibility level for file artifacts: "public" or "private"
                (default: "private"). Public artifacts are viewable by all authenticated
                users on the platform. Private artifacts are restricted based on their
                scope/owner fields.

Note: Progress artifacts always use the server default visibility (public), since
they are informational status indicators that anyone watching an execution should
be able to see. The visibility parameter only controls file artifacts.
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


def allocate_file_version_by_ref(
    base_url,
    token,
    artifact_ref,
    execution_id=None,
    visibility=None,
    content_type="text/plain",
    name=None,
    description=None,
):
    """Upsert an artifact by ref and allocate a file-backed version.

    Single API call that creates the artifact if it doesn't exist (or
    reuses the existing one) and allocates a new version with a file_path.

    Returns:
        (artifact_id, version_id, file_path) tuple
    """
    payload = {
        "scope": "action",
        "owner": "python_example.artifact_demo",
        "type": "file_text",
        "retention_policy": "versions",
        "retention_limit": 10,
        "content_type": content_type,
        "created_by": "python_example.artifact_demo",
    }
    if execution_id is not None:
        payload["execution"] = execution_id
    if visibility is not None:
        payload["visibility"] = visibility
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description

    resp, _ = api_request(
        base_url,
        f"/api/v1/artifacts/ref/{artifact_ref}/versions/file",
        method="POST",
        data=payload,
        token=token,
    )
    version_data = resp["data"]
    return version_data["artifact"], version_data["id"], version_data["file_path"]


def create_artifact(
    base_url,
    token,
    ref,
    name,
    artifact_type,
    execution_id,
    visibility=None,
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
    if visibility is not None:
        payload["visibility"] = visibility
    if description is not None:
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
        visibility = params.get("visibility", "private")

        # Validate visibility value
        if visibility not in ("public", "private"):
            raise ValueError(
                f"Invalid visibility '{visibility}': must be 'public' or 'private'"
            )

        # Get execution context from environment
        api_url = os.environ.get("ATTUNE_API_URL", "")
        token = os.environ.get("ATTUNE_API_TOKEN", "")
        exec_id_str = os.environ.get("ATTUNE_EXEC_ID", "")
        artifacts_dir = os.environ.get("ATTUNE_ARTIFACTS_DIR", "")
        execution_id = int(exec_id_str) if exec_id_str else None

        if not api_url:
            raise RuntimeError(
                "ATTUNE_API_URL environment variable is not set. "
                "This action must be run by the Attune worker."
            )
        if not token:
            raise RuntimeError(
                "ATTUNE_API_TOKEN environment variable is not set. "
                "This action must be run by the Attune worker."
            )
        if not artifacts_dir:
            raise RuntimeError(
                "ATTUNE_ARTIFACTS_DIR environment variable is not set. "
                "This action must be run by the Attune worker."
            )

        print(
            f"Artifact demo starting: {iterations} iterations, "
            f"visibility={visibility}, API at {api_url}, "
            f"artifacts_dir={artifacts_dir}",
            file=sys.stderr,
        )

        # ----------------------------------------------------------------
        # File artifact — single call upserts artifact + allocates version
        # ----------------------------------------------------------------
        file_ref = "python_example.artifact_demo.log"

        file_artifact_id, version_id, file_path = allocate_file_version_by_ref(
            base_url=api_url,
            token=token,
            artifact_ref=file_ref,
            execution_id=execution_id,
            visibility=visibility,
            content_type="text/plain",
            name="Demo Log",
            description="Log output from the artifact demo action",
        )
        full_file_path = os.path.join(artifacts_dir, file_path)
        print(
            f"Allocated file artifact ref={file_ref} id={file_artifact_id} "
            f"version={version_id} path={file_path}",
            file=sys.stderr,
        )

        # ----------------------------------------------------------------
        # Progress artifact — per-execution (ephemeral status indicator)
        # ----------------------------------------------------------------
        ts = int(time.time())
        ref_suffix = f"{execution_id}_{ts}" if execution_id else str(ts)
        progress_ref = f"python_example.artifact_demo.progress.{ref_suffix}"

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
            f"Created progress artifact ID={progress_artifact_id} ref={progress_ref} "
            f"visibility=public (server default)",
            file=sys.stderr,
        )

        # ----------------------------------------------------------------
        # Run iterations — collect log lines, write file at the end
        # ----------------------------------------------------------------
        log_lines = []
        for i in range(iterations):
            iteration = i + 1
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            pct = min(round(iteration * (100.0 / iterations), 1), 100.0)

            # Build log line
            log_line = f"[{now}] Iteration {iteration}/{iterations} — progress {pct}%"
            log_lines.append(log_line)

            print(f"  Iteration {iteration}/{iterations} ({pct}%)", file=sys.stderr)

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

        # ----------------------------------------------------------------
        # Write the complete log file to the shared artifact volume
        # ----------------------------------------------------------------
        full_log = "\n".join(log_lines) + "\n"
        with open(full_file_path, "w", encoding="utf-8") as f:
            f.write(full_log)
        print(
            f"Wrote {len(full_log)} bytes to {full_file_path}",
            file=sys.stderr,
        )

        elapsed = round(time.time() - start_time, 3)
        result = {
            "file_artifact_id": file_artifact_id,
            "file_artifact_ref": file_ref,
            "file_version_id": version_id,
            "file_path": file_path,
            "progress_artifact_id": progress_artifact_id,
            "iterations_completed": iterations,
            "visibility": visibility,
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
