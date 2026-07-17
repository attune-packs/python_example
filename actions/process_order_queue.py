#!/usr/bin/env python3
"""
Process Order Queue Action - Python Example Pack

Demonstrates the standard work-queue contract for Python actions.

Input (stdin JSON):
  items - array of order-like queue payloads
  queue_items - array of Attune queue item metadata aligned with `items`
  queue - Attune-injected queue metadata containing leased item ids and the
          expected ack contract version

Each item can drive a different acknowledgement outcome:
  - completed: normal fulfillment
  - retry: transient issue such as back-ordered inventory
  - failed: permanent validation problem
  - skipped: intentionally deferred for manual review
"""

import attune


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def require_item_id(order, queue_item, index):
    candidate = None
    if isinstance(queue_item, dict):
        candidate = queue_item.get("id")
    if candidate is None:
        candidate = order.get("queue_item_id")
    if candidate is None:
        raise ValueError(
            f"Missing queue item id for batch position {index}; expected queue_items[{index}].id"
        )
    return int(candidate)


def classify_order(order):
    order_id = order.get("order_id", "unknown-order")
    sku = order.get("sku", "unknown-sku")
    quantity = int(order.get("quantity", 1))
    amount = float(order.get("amount", 0))
    inventory_available = as_bool(order.get("inventory_available", True))
    retryable = as_bool(order.get("retryable", False))
    manual_review = as_bool(order.get("requires_manual_review", False))

    if quantity <= 0:
        return (
            "failed",
            None,
            {
                "code": "invalid_quantity",
                "message": f"Order {order_id} for {sku} has invalid quantity {quantity}",
            },
        )

    if amount < 0:
        return (
            "failed",
            None,
            {
                "code": "invalid_amount",
                "message": f"Order {order_id} has invalid amount {amount}",
            },
        )

    if manual_review:
        return (
            "skipped",
            {
                "reason": "manual_review",
                "message": f"Order {order_id} was routed to manual review",
            },
            None,
        )

    if not inventory_available and retryable:
        return (
            "retry",
            None,
            {
                "code": "inventory_backorder",
                "message": f"Inventory for {sku} is temporarily unavailable",
            },
        )

    if not inventory_available:
        return (
            "failed",
            None,
            {
                "code": "inventory_unavailable",
                "message": f"Inventory for {sku} is unavailable and not retryable",
            },
        )

    return (
        "completed",
        {
            "reservation_id": f"res-{order_id}",
            "fulfilled_quantity": quantity,
            "amount": amount,
        },
        None,
    )


def main(items, queue_items=None, queue=None):
    queue = queue or {}

    if not isinstance(items, list) or not items:
        raise ValueError("Expected a non-empty 'items' array")

    if queue_items is not None and not isinstance(queue_items, list):
        raise ValueError("Expected 'queue_items' to be an array when provided")
    if isinstance(queue_items, list) and len(queue_items) != len(items):
        raise ValueError("Length of 'queue_items' must match 'items'")

    ack_version = int(queue.get("ack_contract_version", 1))
    queue_ref = queue.get("ref", "manual.queue")

    ack_items = []
    processed_orders = []
    counts = {"completed": 0, "retry": 0, "failed": 0, "skipped": 0}

    for index, order in enumerate(items):
        if not isinstance(order, dict):
            raise ValueError(f"Queue payload at index {index} must be an object")

        queue_item = queue_items[index] if isinstance(queue_items, list) else {}
        item_id = require_item_id(order, queue_item, index)

        status, summary, error = classify_order(order)
        counts[status] += 1

        ack_item = {"id": item_id, "status": status}
        if summary is not None:
            ack_item["summary"] = summary
        if error is not None:
            ack_item["error"] = error
        ack_items.append(ack_item)

        processed_orders.append(
            {
                "queue_item_id": item_id,
                "order_id": order.get("order_id"),
                "customer": order.get("customer"),
                "sku": order.get("sku"),
                "status": status,
                "summary": summary,
                "error": error,
            }
        )

    return {
        "queue_ref": queue_ref,
        "processed_count": len(items),
        "completed_count": counts["completed"],
        "retry_count": counts["retry"],
        "failed_count": counts["failed"],
        "skipped_count": counts["skipped"],
        "processed_orders": processed_orders,
        "queue_ack": {
            "version": ack_version,
            "items": ack_items,
        },
    }


if __name__ == "__main__":
    attune.run_action(main)
