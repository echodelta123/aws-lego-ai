"""
guardrails.py
-------------
Hallucination detection for the LEGO Recommendation Engine.

The Bedrock Agent can occasionally hallucinate product IDs or names that don't
exist in the catalogue.  This module cross-checks every recommendation against
the live product catalogue in DynamoDB and removes (rather than silently passing)
any item that cannot be verified.

Design principle:
    It is always safer to return fewer verified results than to surface a single
    hallucinated one.  The UI layer handles empty/short result sets gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

CATALOGUE_TABLE = os.environ.get("CATALOGUE_TABLE_NAME", "lego-product-catalogue")


class HallucinationGuard:
    """Validates agent-generated recommendations against the live DynamoDB catalogue."""

    def __init__(self) -> None:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._table = dynamodb.Table(CATALOGUE_TABLE)

    def validate(self, recommendations: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Check each recommendation's product_id exists in the catalogue.

        Returns a dict with:
            passed   (bool)  – True if all items are verified
            safe_items       – list of verified recommendations only
            removed          – list of product_ids that were removed
        """
        safe_items: list[dict[str, Any]] = []
        removed: list[str] = []

        for item in recommendations:
            product_id = item.get("product_id", "")
            if self._product_exists(product_id):
                safe_items.append(item)
            else:
                logger.warning("Hallucination guard: product_id '%s' not found in catalogue", product_id)
                removed.append(product_id)

        return {
            "passed": len(removed) == 0,
            "safe_items": safe_items,
            "removed": removed,
        }

    def _product_exists(self, product_id: str) -> bool:
        """Return True if the product_id has an active record in DynamoDB."""
        if not product_id:
            return False
        try:
            response = self._table.get_item(
                Key={"product_id": product_id},
                ProjectionExpression="product_id, active",
            )
            item = response.get("Item")
            return item is not None and item.get("active", False)
        except Exception as exc:
            # If the catalogue is temporarily unavailable, fail safe by rejecting the item
            logger.error("Catalogue lookup failed for product_id '%s': %s", product_id, exc)
            return False
