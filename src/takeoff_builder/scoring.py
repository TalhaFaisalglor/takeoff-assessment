from __future__ import annotations

from collections import defaultdict
from math import isclose

from .models import TakeoffItem


def normalize_description(value: str) -> str:
    return " ".join(value.lower().replace("_x000d_", " ").split())


def score_predictions(predicted: list[TakeoffItem], gold: list[TakeoffItem]) -> dict[str, object]:
    gold_lookup: dict[str, list[TakeoffItem]] = defaultdict(list)
    predicted_lookup: dict[str, list[TakeoffItem]] = defaultdict(list)
    for item in gold:
        gold_lookup[normalize_description(item.description)].append(item)
    for item in predicted:
        predicted_lookup[normalize_description(item.description)].append(item)

    matched_items = 0
    missing_items: list[str] = []
    extra_items: list[str] = []
    quantity_differences: list[dict[str, object]] = []

    for desc, gold_items in gold_lookup.items():
        predicted_items = predicted_lookup.get(desc, [])
        if not predicted_items:
            missing_items.extend(item.description for item in gold_items)
            continue
        paired = min(len(gold_items), len(predicted_items))
        matched_items += paired
        if len(predicted_items) < len(gold_items):
            missing_items.extend(item.description for item in gold_items[paired:])
        if len(predicted_items) > len(gold_items):
            extra_items.extend(item.description for item in predicted_items[paired:])
        for left, right in zip(predicted_items[:paired], gold_items[:paired]):
            if not _quantity_matches(left.quantity, right.quantity):
                quantity_differences.append(
                    {
                        "description": right.description,
                        "predicted_quantity": left.quantity,
                        "gold_quantity": right.quantity,
                        "unit": right.unit,
                    }
                )

    for desc, predicted_items in predicted_lookup.items():
        if desc not in gold_lookup:
            extra_items.extend(item.description for item in predicted_items)

    precision = matched_items / max(len(predicted), 1)
    recall = matched_items / max(len(gold), 1)
    return {
        "matched_items": matched_items,
        "missing_items": missing_items,
        "extra_items": extra_items,
        "quantity_differences": quantity_differences,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "overall_notes": "Exact description matching with quantity comparison tolerance of 5%.",
    }


def _quantity_matches(left: float | int | None, right: float | int | None) -> bool:
    if left is None or right is None:
        return left == right
    return isclose(float(left), float(right), rel_tol=0.05, abs_tol=1.0)
