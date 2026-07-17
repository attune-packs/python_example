#!/usr/bin/env python3
"""
Artifact Demo Action - Python Example Pack

Demonstrates creating file and progress artifacts with the Attune SDK artifact
helpers.

Each iteration:
  1. Appends a line to an in-memory log
  2. Updates a progress artifact
  3. Sleeps for 0.5 seconds

After all iterations complete, the full log is written as a single version to a
stable file artifact ref (`python_example.artifact_demo.log`).

Parameters:
  iterations  - Number of iterations to run (default: 50)
  visibility  - Artifact visibility level: "public" or "private" (default:
                "private")
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
import sys

import attune


def _parse_execution_id(value: str) -> int | None:
    if not value:
        return None
    return int(value)


def main(iterations: int = 50, visibility: str = "private"):
    start_time = time.time()

    if visibility not in ("public", "private"):
        raise ValueError(f"Invalid visibility '{visibility}': must be 'public' or 'private'")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    ctx = attune.context
    execution_id = _parse_execution_id(ctx.execution_id)

    print(
        f"Artifact demo starting: {iterations} iterations, visibility={visibility}, "
        f"API at {ctx.api_url}, artifacts_dir={ctx.artifacts_dir}",
        file=sys.stderr,
    )

    file_ref = "python_example.artifact_demo.log"
    file_allocation = attune.artifacts.allocate_file_version(
        artifact_ref=file_ref,
        visibility=visibility,
        execution=execution_id,
        content_type="text/plain",
        name="Demo Log",
        description="Log output from the artifact demo action",
        retention_policy="versions",
        retention_limit=10,
    )
    print(
        f"Allocated file artifact ref={file_ref} id={file_allocation.artifact_id} "
        f"version={file_allocation.version_id} path={file_allocation.file_path}",
        file=sys.stderr,
    )

    ts = int(time.time())
    ref_suffix = f"{execution_id}_{ts}" if execution_id else str(ts)
    progress_ref = f"python_example.artifact_demo.progress.{ref_suffix}"

    progress_artifact = attune.artifacts.create_progress(
        artifact_ref=progress_ref,
        visibility=visibility,
        name="Artifact Demo Progress",
        description=f"Progress tracker for artifact demo ({iterations} iterations)",
        data=[],
        retention_policy="versions",
        retention_limit=10,
        reuse_existing=False,
    )
    print(
        f"Created progress artifact ID={progress_artifact.artifact_id} ref={progress_ref} "
        f"visibility={progress_artifact.visibility}",
        file=sys.stderr,
    )

    log_lines: list[str] = []
    for i in range(iterations):
        iteration = i + 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        pct = min(round(iteration * (100.0 / iterations), 1), 100.0)

        log_line = f"[{now}] Iteration {iteration}/{iterations} - progress {pct}%"
        log_lines.append(log_line)

        print(f"  Iteration {iteration}/{iterations} ({pct}%)", file=sys.stderr)
        progress_artifact.append(
            {
                "iteration": iteration,
                "total": iterations,
                "percent": pct,
                "message": f"Completed iteration {iteration}",
                "timestamp": now,
            },
        )

        if iteration < iterations:
            time.sleep(0.5)

    full_log = "\n".join(log_lines) + "\n"
    full_file_path = file_allocation.write_text(full_log, encoding="utf-8")
    print(f"Wrote {len(full_log)} bytes to {full_file_path}", file=sys.stderr)

    elapsed = round(time.time() - start_time, 3)
    print(f"Artifact demo completed in {elapsed}s", file=sys.stderr)
    return {
        "file_artifact_id": file_allocation.artifact_id,
        "file_artifact_ref": file_ref,
        "file_version_id": file_allocation.version_id,
        "file_path": file_allocation.file_path,
        "progress_artifact_id": progress_artifact.artifact_id,
        "iterations_completed": iterations,
        "visibility": visibility,
        "elapsed_seconds": elapsed,
        "success": True,
    }


if __name__ == "__main__":
    attune.run_action(main)
