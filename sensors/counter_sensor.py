#!/usr/bin/env python3
"""
Counter sensor implemented with the Attune Python SDK.

This sensor demonstrates the current managed-sensor model:
- bootstrap from ATTUNE_SENSOR_TRIGGERS
- live rule lifecycle updates via the notifier WebSocket
- per-rule polling managed by attune.PollingSensor
- event emission via Sensor.emit()
- persistent per-rule counter state stored in the Attune keystore
"""

from __future__ import annotations

import threading
from hashlib import sha256
from datetime import datetime, timezone
from typing import Any

import httpx

import attune


class CounterSensor(attune.PollingSensor):
    interval: float = 1.0

    def setup(self) -> None:
        config = attune.sensor_context.config
        self._rule_locks: dict[int, threading.Lock] = {}
        self._rule_locks_guard = threading.Lock()
        self._fatal_error: str | None = None
        self._fatal_error_guard = threading.Lock()
        try:
            self.interval = float(config.get("default_interval_seconds", "1"))
        except ValueError:
            self.interval = 1.0

        self.logger.info(
            "Counter sensor configured",
            extra={
                "default_interval_seconds": self.interval,
                "sensor_ref": attune.sensor_context.sensor_ref,
            },
        )

    def run(self) -> None:
        while not self.is_shutting_down:
            fatal = self._fatal_error_message()
            if fatal:
                raise RuntimeError(fatal)
            self._shutdown_event.wait(timeout=1)

        fatal = self._fatal_error_message()
        if fatal:
            raise RuntimeError(fatal)

    def poll(self, rule: attune.RuleState) -> None:
        with self._rule_lock(rule.rule_id):
            key_ref = self._key_ref(rule)
            current_value = self._read_counter(key_ref)
            if self._fatal_error_message() is not None:
                return

            next_value = current_value + 1
            event_id = self._emit_counter_event(rule, next_value)
            if event_id is None:
                self.logger.warning(
                    "Counter event emission failed; skipping counter advance",
                    extra={
                        "rule_id": rule.rule_id,
                        "rule_ref": rule.rule_ref,
                        "key_ref": key_ref,
                        "counter": next_value,
                    },
                )
                return

            self._write_counter(key_ref, next_value)
            if self._fatal_error_message() is not None:
                return

            self.logger.info(
                "Counter emitted",
                extra={
                    "rule_id": rule.rule_id,
                    "rule_ref": rule.rule_ref,
                    "key_ref": key_ref,
                    "counter": next_value,
                    "event_id": event_id,
                },
            )

    def on_rule_created(self, rule: attune.RuleState) -> None:
        super().on_rule_created(rule)
        self.logger.info(
            "Rule created",
            extra={"rule_id": rule.rule_id, "rule_ref": rule.rule_ref},
        )

    def on_rule_enabled(self, rule: attune.RuleState) -> None:
        super().on_rule_enabled(rule)
        self.logger.info(
            "Rule enabled",
            extra={"rule_id": rule.rule_id, "rule_ref": rule.rule_ref},
        )

    def on_rule_disabled(self, rule: attune.RuleState) -> None:
        super().on_rule_disabled(rule)
        self.logger.info(
            "Rule disabled",
            extra={"rule_id": rule.rule_id, "rule_ref": rule.rule_ref},
        )

    def on_rule_deleted(self, rule: attune.RuleState) -> None:
        super().on_rule_deleted(rule)
        self.logger.info(
            "Rule deleted",
            extra={"rule_id": rule.rule_id, "rule_ref": rule.rule_ref},
        )

    def on_rule_updated(
        self, rule: attune.RuleState, old_params: dict[str, Any]
    ) -> None:
        super().on_rule_updated(rule, old_params)
        self.logger.info(
            "Rule updated",
            extra={
                "rule_id": rule.rule_id,
                "rule_ref": rule.rule_ref,
                "old_params": old_params,
                "new_params": rule.trigger_params,
            },
        )

    def _key_ref(self, rule: attune.RuleState) -> str:
        rule_digest = sha256(rule.rule_ref.encode("utf-8")).hexdigest()[:24]
        local_ref = f"counter_{rule_digest}"
        return f"sensor.{attune.sensor_context.sensor_ref}.{local_ref}"

    def _rule_lock(self, rule_id: int) -> threading.Lock:
        with self._rule_locks_guard:
            return self._rule_locks.setdefault(rule_id, threading.Lock())

    def _read_counter(self, key_ref: str) -> int:
        try:
            response = self._request_with_auth_retry("GET", f"/api/v1/keys/{key_ref}")
            if response is None:
                return 0
            if response.status_code == 404:
                return 0
            response.raise_for_status()
            payload = response.json().get("data", {})
            value = payload.get("value", 0)
            return int(value)
        except (ValueError, TypeError):
            self.logger.warning("Invalid counter value for %s; resetting to 0", key_ref)
            return 0
        except httpx.HTTPError as exc:
            self.logger.error("Failed to read counter key %s: %s", key_ref, exc)
            return 0

    def _write_counter(self, key_ref: str, value: int) -> None:
        body = {"value": value, "name": f"Counter: {key_ref}"}
        try:
            response = self._request_with_auth_retry(
                "PUT", f"/api/v1/keys/{key_ref}", json=body
            )
            if response is None:
                return
            if response.status_code in (200, 201):
                return
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

        owner_prefix = f"sensor.{attune.sensor_context.sensor_ref}."
        local_ref = key_ref.removeprefix(owner_prefix)
        create_body = {
            "local_ref": local_ref,
            "owner_type": "sensor",
            "owner_sensor_ref": attune.sensor_context.sensor_ref,
            "name": f"Counter: {key_ref}",
            "value": value,
            "encrypted": False,
        }
        response = self._request_with_auth_retry(
            "POST", "/api/v1/keys", json=create_body
        )
        if response is None:
            return
        if response.status_code in (200, 201, 409):
            if response.status_code == 409:
                retry = self._request_with_auth_retry(
                    "PUT", f"/api/v1/keys/{key_ref}", json=body
                )
                if retry is None:
                    return
                retry.raise_for_status()
            return
        response.raise_for_status()

    def _emit_counter_event(self, rule: attune.RuleState, counter: int) -> int | None:
        body = {
            "trigger_ref": rule.trigger_ref or attune.sensor_context.sensor_ref,
            "payload": {
                "counter": counter,
                "rule_ref": rule.rule_ref,
                "sensor_ref": attune.sensor_context.sensor_ref,
                "fired_at": datetime.now(timezone.utc).isoformat(),
            },
            "source": attune.sensor_context.sensor_ref,
            "trigger_instance_id": f"rule_{rule.rule_id}",
        }

        try:
            response = self._request_with_auth_retry(
                "POST", "/api/v1/events", json=body
            )
            if response is None:
                return None
            response.raise_for_status()
            return response.json().get("data", {}).get("id")
        except httpx.HTTPError as exc:
            self.logger.error("Failed to emit event: %s", exc)
            return None

    def _request_with_auth_retry(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response | None:
        response = self.http_client.request(method, path, **kwargs)
        if response.status_code != 401:
            return response

        self.logger.warning(
            "Sensor API request unauthorized; rebuilding client and retrying once",
            extra={"method": method, "path": path},
        )
        self._rebuild_http_client()
        retry = self.http_client.request(method, path, **kwargs)
        if retry.status_code == 401:
            self._mark_fatal_auth_failure(method, path)
            return None
        return retry

    def _mark_fatal_auth_failure(self, method: str, path: str) -> None:
        reason = (
            f"Unrecoverable sensor auth failure ({method} {path}); "
            "requesting process restart"
        )
        with self._fatal_error_guard:
            if self._fatal_error is not None:
                return
            self._fatal_error = reason

        self.logger.error(reason)
        self.shutdown()

    def _fatal_error_message(self) -> str | None:
        with self._fatal_error_guard:
            return self._fatal_error


if __name__ == "__main__":
    attune.run_sensor(CounterSensor)
