"""
audit_logger.py
---------------
Writes model input/output and decision context to a DynamoDB audit table.

Every inference — success or failure — is recorded here.  This table is the
authoritative source for:
  - Debugging individual customer complaints
  - Compliance audits requiring explainability
  - Monitoring for unexpected output patterns
  - Linking recommendations back to the model version that produced them

The write is best-effort (non-critical path), but failures are surfaced as
CloudWatch metrics so they are visible in the operational dashboard.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)

AUDIT_TABLE = os.environ.get("AUDIT_TABLE_NAME", "lego-recommendation-audit")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")


class AuditLogger:
    def __init__(self) -> None:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._table = dynamodb.Table(AUDIT_TABLE)
        self._cloudwatch = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def record_success(
        self,
        request_id: str,
        customer_id: str,
        query: str,
        agent_response: dict[str, Any],
    ) -> None:
        """Record a successful recommendation inference."""
        self._write(
            request_id=request_id,
            customer_id=customer_id,
            query_hash=_hash(query),  # hash PII — never log raw query text
            outcome="success",
            num_recommendations=len(agent_response.get("recommendations", [])),
            guardrail_triggered=agent_response.get("guardrail_triggered", False),
            model_version=MODEL_VERSION,
        )

    def record_failure(self, request_id: str, customer_id: str, error_summary: str) -> None:
        """Record a failed inference attempt."""
        self._write(
            request_id=request_id,
            customer_id=customer_id,
            outcome="failure",
            error_summary=error_summary[:500],  # cap length
            model_version=MODEL_VERSION,
        )
        self._emit_failure_metric()

    def _write(self, **item_fields: Any) -> None:
        item = {
            "request_id": item_fields.pop("request_id"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ttl": _ttl_90_days(),
            **item_fields,
        }
        try:
            self._table.put_item(Item=item)
        except Exception as exc:
            logger.error("Audit write failed for request_id=%s: %s", item.get("request_id"), exc)

    def _emit_failure_metric(self) -> None:
        try:
            self._cloudwatch.put_metric_data(
                Namespace="LegoRecommendation",
                MetricData=[{"MetricName": "InferenceFailures", "Value": 1, "Unit": "Count"}],
            )
        except Exception as exc:
            logger.warning("CloudWatch metric emission failed: %s", exc)


def _hash(text: str) -> str:
    """SHA-256 hash — used so we can correlate logs without storing raw PII."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ttl_90_days() -> int:
    """Return a Unix timestamp 90 days from now for DynamoDB TTL."""
    from datetime import timedelta

    return int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())
