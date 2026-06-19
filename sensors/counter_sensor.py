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
from datetime import datetime, timezone
from typing import Any

import attune
import httpx


class CounterSensor(attune.PollingSensor):
    interval: float = 1.0

    def setup(self) -> None:
        config = attune.sensor_context.config
        self.key_prefix = config.get("key_prefix", "python_example.counter")
        self._rule_locks: dict[int, threading.Lock] = {}
        self._rule_locks_guard = threading.Lock()
        try:
            self.interval = float(config.get("default_interval_seconds", "1"))
        except ValueError:
            self.interval = 1.0

        self.logger.info(
            "Counter sensor configured",
            extra={
                "default_interval_seconds": self.interval,
                "key_prefix": self.key_prefix,
                "sensor_ref": attune.sensor_context.sensor_ref,
            },
        )

    def poll(self, rule: attune.RuleState) -> None:
        with self._rule_lock(rule.rule_id):
            key_ref = self._key_ref(rule)
            current_value = self._read_counter(key_ref)
            next_value = current_value + 1

            event_id = self.emit(
                {
                    "counter": next_value,
                    "rule_ref": rule.rule_ref,
                    "sensor_ref": attune.sensor_context.sensor_ref,
                    "fired_at": datetime.now(timezone.utc).isoformat(),
                },
                rule=rule,
                target_rule=True,
            )
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
        return f"{self.key_prefix}.{rule.rule_ref.replace('.', '_')}"

    def _rule_lock(self, rule_id: int) -> threading.Lock:
        with self._rule_locks_guard:
            return self._rule_locks.setdefault(rule_id, threading.Lock())

    def _read_counter(self, key_ref: str) -> int:
        try:
            response = self.http_client.get(f"/api/v1/keys/{key_ref}")
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
            response = self.http_client.put(f"/api/v1/keys/{key_ref}", json=body)
            if response.status_code in (200, 201):
                return
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

        create_body = {
            "ref": key_ref,
            "owner_type": "sensor",
            "owner_sensor_ref": attune.sensor_context.sensor_ref,
            "name": f"Counter: {key_ref}",
            "value": value,
            "encrypted": False,
        }
        response = self.http_client.post("/api/v1/keys", json=create_body)
        if response.status_code in (200, 201, 409):
            if response.status_code == 409:
                retry = self.http_client.put(f"/api/v1/keys/{key_ref}", json=body)
                retry.raise_for_status()
            return
        response.raise_for_status()


if __name__ == "__main__":
    attune.run_sensor(CounterSensor)
