"""
tests/test_guardrails.py
------------------------
Unit tests for the HallucinationGuard — validates that the guard correctly
rejects product IDs that are not in the catalogue and passes valid ones.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from guardrails import HallucinationGuard


def _make_guard(existing_products: set[str]) -> HallucinationGuard:
    """Return a HallucinationGuard whose DynamoDB table is mocked."""
    guard = HallucinationGuard.__new__(HallucinationGuard)

    mock_table = MagicMock()

    def fake_get_item(Key, **kwargs):
        pid = Key.get("product_id", "")
        if pid in existing_products:
            return {"Item": {"product_id": pid, "active": True}}
        return {}

    mock_table.get_item.side_effect = fake_get_item
    guard._table = mock_table
    return guard


class TestHallucinationGuard:
    def test_all_valid_products_pass(self):
        guard = _make_guard({"PROD-001", "PROD-002"})
        result = guard.validate([
            {"product_id": "PROD-001", "name": "Space Shuttle", "reason": "Great for space fans", "price_gbp": 49.99},
            {"product_id": "PROD-002", "name": "City Police", "reason": "Popular with kids", "price_gbp": 29.99},
        ])
        assert result["passed"] is True
        assert len(result["safe_items"]) == 2
        assert result["removed"] == []

    def test_hallucinated_product_is_removed(self):
        guard = _make_guard({"PROD-001"})
        result = guard.validate([
            {"product_id": "PROD-001", "name": "Space Shuttle", "reason": "Great for space fans", "price_gbp": 49.99},
            {"product_id": "HALLUCINATED-999", "name": "Fake Set", "reason": "Does not exist", "price_gbp": 99.99},
        ])
        assert result["passed"] is False
        assert len(result["safe_items"]) == 1
        assert "HALLUCINATED-999" in result["removed"]

    def test_all_hallucinated_returns_empty_list(self):
        guard = _make_guard(set())
        result = guard.validate([
            {"product_id": "FAKE-A", "name": "A", "reason": "x", "price_gbp": 1.0},
            {"product_id": "FAKE-B", "name": "B", "reason": "y", "price_gbp": 2.0},
        ])
        assert result["passed"] is False
        assert result["safe_items"] == []
        assert len(result["removed"]) == 2

    def test_empty_product_id_is_rejected(self):
        guard = _make_guard({"PROD-001"})
        result = guard.validate([{"product_id": "", "name": "No ID", "reason": "missing", "price_gbp": 0.0}])
        assert result["passed"] is False
        assert result["safe_items"] == []

    def test_catalogue_failure_fails_safe(self):
        """If DynamoDB is down, the guard must reject (not accept) the item."""
        guard = _make_guard(set())
        guard._table.get_item.side_effect = Exception("DynamoDB connection error")
        result = guard.validate([{"product_id": "PROD-001", "name": "Shuttle", "reason": "ok", "price_gbp": 10.0}])
        assert result["passed"] is False
        assert result["safe_items"] == []

    def test_empty_input_passes_trivially(self):
        guard = _make_guard(set())
        result = guard.validate([])
        assert result["passed"] is True
        assert result["safe_items"] == []
        assert result["removed"] == []
