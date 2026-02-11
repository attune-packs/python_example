#!/usr/bin/env python3
"""
Counter Sensor - Python Example Pack

A stateful Python sensor that demonstrates:
- RabbitMQ integration for rule lifecycle events
- Attune keystore API for persistent per-rule counter state
- Periodic event emission via the Attune events API
- Per-rule scoped counters with independent timer threads
- Graceful shutdown with thread cleanup

Environment Variables (provided by attune-sensor service):
    ATTUNE_API_URL      - Base URL of the Attune API (e.g. http://localhost:8080)
    ATTUNE_API_TOKEN    - JWT token for authenticating API calls
    ATTUNE_SENSOR_ID    - Database ID of this sensor instance
    ATTUNE_SENSOR_REF   - Reference name (python_example.counter_sensor)
    ATTUNE_MQ_URL       - RabbitMQ connection URL (e.g. amqp://localhost:5672)
    ATTUNE_MQ_EXCHANGE  - RabbitMQ exchange name (default: attune)
    ATTUNE_LOG_LEVEL    - Logging verbosity (default: info)
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import pika
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = os.environ.get("ATTUNE_API_URL", "http://localhost:8080")
API_TOKEN = os.environ.get("ATTUNE_API_TOKEN", "")
SENSOR_ID = os.environ.get("ATTUNE_SENSOR_ID", "0")
SENSOR_REF = os.environ.get("ATTUNE_SENSOR_REF", "python_example.counter_sensor")
MQ_URL = os.environ.get("ATTUNE_MQ_URL", "amqp://localhost:5672")
MQ_EXCHANGE = os.environ.get("ATTUNE_MQ_EXCHANGE", "attune")
LOG_LEVEL = os.environ.get("ATTUNE_LOG_LEVEL", "info").upper()

TRIGGER_TYPE = "python_example.counter"
KEY_PREFIX = "python_example.counter"
DEFAULT_INTERVAL = 1  # seconds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("counter_sensor")


def log_json(level, message, **extra):
    """Emit a structured JSON log line to stderr."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "sensor": SENSOR_REF,
        "message": message,
        **extra,
    }
    print(json.dumps(entry), file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _api_headers():
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }


def keystore_get(key_ref):
    """Read a key from the Attune keystore. Returns the value or None."""
    try:
        resp = requests.get(
            f"{API_URL}/api/v1/keys/{key_ref}",
            headers=_api_headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return data.get("value")
        if resp.status_code == 404:
            return None
        log_json(
            "warn",
            "keystore GET unexpected status",
            key=key_ref,
            status=resp.status_code,
        )
        return None
    except requests.RequestException as exc:
        log_json("error", "keystore GET failed", key=key_ref, error=str(exc))
        return None


def keystore_put(key_ref, value):
    """Update an existing key in the Attune keystore."""
    try:
        resp = requests.put(
            f"{API_URL}/api/v1/keys/{key_ref}",
            headers=_api_headers(),
            json={"value": str(value), "name": f"Counter: {key_ref}"},
            timeout=5,
        )
        if resp.status_code not in (200, 201):
            log_json(
                "warn",
                "keystore PUT unexpected status",
                key=key_ref,
                status=resp.status_code,
            )
        return resp.status_code in (200, 201)
    except requests.RequestException as exc:
        log_json("error", "keystore PUT failed", key=key_ref, error=str(exc))
        return False


def keystore_create(key_ref, value, rule_ref):
    """Create a new key in the Attune keystore."""
    try:
        resp = requests.post(
            f"{API_URL}/api/v1/keys",
            headers=_api_headers(),
            json={
                "ref": key_ref,
                "owner_type": "sensor",
                "owner_sensor_ref": SENSOR_REF,
                "name": f"Counter: {key_ref}",
                "value": str(value),
                "encrypted": False,
            },
            timeout=5,
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code == 409:
            # Key already exists (race condition) — update instead
            return keystore_put(key_ref, value)
        log_json(
            "warn",
            "keystore POST unexpected status",
            key=key_ref,
            status=resp.status_code,
        )
        return False
    except requests.RequestException as exc:
        log_json("error", "keystore POST failed", key=key_ref, error=str(exc))
        return False


def emit_event(payload, rule_ref):
    """Create an event via POST /events."""
    body = {
        "trigger_type": TRIGGER_TYPE,
        "payload": payload,
        "trigger_instance_id": f"rule_{rule_ref}",
    }
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{API_URL}/api/v1/events",
                headers=_api_headers(),
                json=body,
                timeout=5,
            )
            if resp.status_code in (200, 201):
                return True
            log_json(
                "warn",
                "event POST unexpected status",
                status=resp.status_code,
                attempt=attempt + 1,
                rule_ref=rule_ref,
            )
        except requests.RequestException as exc:
            log_json("error", "event POST failed", error=str(exc), attempt=attempt + 1)
        # Exponential backoff
        time.sleep(0.5 * (2**attempt))
    return False


# ---------------------------------------------------------------------------
# Per-rule counter loop
# ---------------------------------------------------------------------------


class RuleCounter:
    """Manages a per-rule counter with a background timer thread."""

    def __init__(self, rule_id, rule_ref, trigger_params):
        self.rule_id = rule_id
        self.rule_ref = rule_ref
        self.interval = trigger_params.get("interval_seconds", DEFAULT_INTERVAL)
        self.key_ref = f"{KEY_PREFIX}.{rule_ref.replace('.', '_')}"
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        """Start the counter loop in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"counter-{self.rule_ref}",
            daemon=True,
        )
        self._thread.start()
        log_json(
            "info",
            "counter started",
            rule_id=self.rule_id,
            rule_ref=self.rule_ref,
            interval=self.interval,
        )

    def stop(self):
        """Signal the counter loop to stop and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        log_json(
            "info", "counter stopped", rule_id=self.rule_id, rule_ref=self.rule_ref
        )

    def _loop(self):
        """Main counter loop: read → increment → write → emit, repeat."""
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                log_json(
                    "error",
                    "counter tick failed",
                    rule_ref=self.rule_ref,
                    error=str(exc),
                )
            self._stop.wait(timeout=self.interval)

    def _tick(self):
        """Execute one counter cycle."""
        # Read current value from keystore
        raw = keystore_get(self.key_ref)
        if raw is not None:
            try:
                counter = int(raw)
            except (ValueError, TypeError):
                counter = 0
        else:
            counter = 0

        # Increment
        counter += 1

        # Write back to keystore
        if raw is None:
            keystore_create(self.key_ref, counter, self.rule_ref)
        else:
            keystore_put(self.key_ref, counter)

        # Build event payload
        payload = {
            "counter": counter,
            "rule_ref": self.rule_ref,
            "sensor_ref": SENSOR_REF,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }

        # Emit event
        emit_event(payload, self.rule_ref)


# ---------------------------------------------------------------------------
# Rule manager
# ---------------------------------------------------------------------------


class RuleManager:
    """Tracks active rules and their counter threads."""

    def __init__(self):
        self._rules = {}  # rule_id -> RuleCounter
        self._lock = threading.Lock()

    def handle_message(self, message):
        """Process a rule lifecycle message from RabbitMQ."""
        event_type = message.get("event_type", "")
        rule_id = message.get("rule_id")
        rule_ref = message.get("rule_ref", f"rule_{rule_id}")
        trigger_type = message.get("trigger_type", "")
        trigger_params = message.get("trigger_params", {})

        # Only handle messages for our trigger type
        if trigger_type and trigger_type != TRIGGER_TYPE:
            return

        if event_type in ("RuleCreated", "RuleEnabled"):
            self._start_rule(rule_id, rule_ref, trigger_params)
        elif event_type in ("RuleDisabled", "RuleDeleted"):
            self._stop_rule(rule_id)
        else:
            log_json("debug", "ignoring unknown event_type", event_type=event_type)

    def _start_rule(self, rule_id, rule_ref, trigger_params):
        with self._lock:
            if rule_id in self._rules:
                # Already tracking — restart with potentially new params
                self._rules[rule_id].stop()
            rc = RuleCounter(rule_id, rule_ref, trigger_params)
            self._rules[rule_id] = rc
            rc.start()

    def _stop_rule(self, rule_id):
        with self._lock:
            rc = self._rules.pop(rule_id, None)
        if rc is not None:
            rc.stop()

    def stop_all(self):
        """Stop all active counter threads."""
        with self._lock:
            rule_ids = list(self._rules.keys())
        for rid in rule_ids:
            self._stop_rule(rid)

    @property
    def active_count(self):
        with self._lock:
            return len(self._rules)


# ---------------------------------------------------------------------------
# RabbitMQ consumer
# ---------------------------------------------------------------------------

ROUTING_KEYS = ["rule.created", "rule.enabled", "rule.disabled", "rule.deleted"]


def start_mq_consumer(rule_manager, shutdown_event):
    """Connect to RabbitMQ and consume rule lifecycle messages.

    Runs in a dedicated thread. Reconnects automatically on failure.
    """
    queue_name = f"sensor.{SENSOR_REF}"

    while not shutdown_event.is_set():
        connection = None
        try:
            log_json("info", "connecting to RabbitMQ", url=MQ_URL)
            params = pika.URLParameters(MQ_URL)
            params.heartbeat = 30
            params.blocked_connection_timeout = 30
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # Declare exchange (idempotent)
            channel.exchange_declare(
                exchange=MQ_EXCHANGE,
                exchange_type="topic",
                durable=True,
            )

            # Declare and bind queue
            channel.queue_declare(queue=queue_name, durable=True)
            for rk in ROUTING_KEYS:
                channel.queue_bind(
                    queue=queue_name,
                    exchange=MQ_EXCHANGE,
                    routing_key=rk,
                )

            log_json("info", "RabbitMQ connected, consuming", queue=queue_name)

            # Consume messages with a timeout so we can check shutdown_event
            for method, _properties, body in channel.consume(
                queue=queue_name,
                inactivity_timeout=1,
            ):
                if shutdown_event.is_set():
                    break

                if method is None:
                    # Inactivity timeout — just loop to check shutdown
                    continue

                try:
                    message = json.loads(body)
                    log_json(
                        "debug",
                        "received MQ message",
                        event_type=message.get("event_type"),
                    )
                    rule_manager.handle_message(message)
                except json.JSONDecodeError:
                    log_json(
                        "warn",
                        "invalid JSON in MQ message",
                        body=body.decode("utf-8", errors="replace")[:200],
                    )
                except Exception as exc:
                    log_json("error", "error processing MQ message", error=str(exc))

                channel.basic_ack(delivery_tag=method.delivery_tag)

        except pika.exceptions.AMQPConnectionError as exc:
            log_json(
                "warn", "RabbitMQ connection error, retrying in 5s", error=str(exc)
            )
        except Exception as exc:
            log_json("error", "unexpected MQ error, retrying in 5s", error=str(exc))
        finally:
            if connection and not connection.is_closed:
                try:
                    connection.close()
                except Exception:
                    pass

        # Wait before reconnecting (unless shutting down)
        shutdown_event.wait(timeout=5)


# ---------------------------------------------------------------------------
# Bootstrap: fetch existing active rules on startup
# ---------------------------------------------------------------------------


def fetch_active_rules(rule_manager):
    """Query the API for rules that reference our trigger type and start counters."""
    try:
        resp = requests.get(
            f"{API_URL}/api/v1/rules",
            headers=_api_headers(),
            params={"trigger_ref": TRIGGER_TYPE, "enabled": "true"},
            timeout=10,
        )
        if resp.status_code != 200:
            log_json("warn", "failed to fetch active rules", status=resp.status_code)
            return

        body = resp.json()
        rules = body.get("data", [])
        if not isinstance(rules, list):
            # Might be paginated — handle the common shapes
            rules = []

        for rule in rules:
            rule_id = rule.get("id")
            rule_ref = rule.get("ref", f"rule_{rule_id}")
            enabled = rule.get("enabled", True)
            if rule_id and enabled:
                rule_manager.handle_message(
                    {
                        "event_type": "RuleCreated",
                        "rule_id": rule_id,
                        "rule_ref": rule_ref,
                        "trigger_type": TRIGGER_TYPE,
                        "trigger_params": rule.get("trigger_params", {}),
                    }
                )

        log_json("info", "bootstrapped active rules", count=len(rules))

    except requests.RequestException as exc:
        log_json("warn", "could not fetch active rules on startup", error=str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    log_json("info", "sensor starting", sensor_ref=SENSOR_REF, api_url=API_URL)

    shutdown_event = threading.Event()
    rule_manager = RuleManager()

    # Handle termination signals
    def _shutdown(signum, _frame):
        sig_name = (
            signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        )
        log_json("info", "shutdown signal received", signal=sig_name)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Bootstrap: load already-active rules from the API
    fetch_active_rules(rule_manager)

    # Start RabbitMQ consumer in a background thread
    mq_thread = threading.Thread(
        target=start_mq_consumer,
        args=(rule_manager, shutdown_event),
        name="mq-consumer",
        daemon=True,
    )
    mq_thread.start()

    log_json("info", "sensor running", active_rules=rule_manager.active_count)

    # Main thread just waits for shutdown
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=10)
            if not shutdown_event.is_set():
                log_json("debug", "heartbeat", active_rules=rule_manager.active_count)
    except KeyboardInterrupt:
        log_json("info", "keyboard interrupt")
        shutdown_event.set()

    # Graceful shutdown
    log_json("info", "shutting down", active_rules=rule_manager.active_count)
    rule_manager.stop_all()

    # Give the MQ thread a moment to clean up
    mq_thread.join(timeout=5)

    log_json("info", "sensor stopped")


if __name__ == "__main__":
    main()
