"""
error_recovery.py
-----------------
Retry logic and dead-letter-queue publishing for unrecoverable agent failures.

Pattern:
  - Transient errors (throttling, network) → exponential backoff with jitter
  - Unrecoverable errors → publish to SQS DLQ with full context for manual review
  - All failures → CloudWatch metric for operational alerting

This module makes the assistant resilient: users experience graceful degradation
(a clear "I cannot help right now" message) rather than stack traces or silent failures.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DLQ_URL = os.environ.get("AGENT_DLQ_URL", "")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
BASE_DELAY_SECONDS = float(os.environ.get("BASE_DELAY_SECONDS", "1.0"))

T = TypeVar("T")

# Error types that are worth retrying
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
}


def with_retry(fn: Callable[[], T], context: str = "") -> T:
    """
    Execute fn with exponential backoff.  Raises the last exception if all
    retries are exhausted.

    Args:
        fn:      Zero-argument callable to retry.
        context: Human-readable description of the operation (for logging).
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code not in RETRYABLE_ERROR_CODES:
                logger.error("Non-retryable error in '%s' (attempt %d): %s", context, attempt, exc)
                raise
            last_exc = exc
        except Exception as exc:
            last_exc = exc

        if attempt < MAX_RETRIES:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Retryable error in '%s' (attempt %d/%d), retrying in %.2fs: %s",
                context, attempt, MAX_RETRIES, delay, last_exc,
            )
            time.sleep(delay)

    logger.error("All %d retries exhausted for '%s'", MAX_RETRIES, context)
    raise last_exc  # type: ignore[misc]


class DeadLetterPublisher:
    """Publishes unrecoverable failures to the SQS dead-letter queue."""

    def __init__(self) -> None:
        self._sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._cw = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def publish(
        self,
        request_id: str,
        user_query: str,
        error_detail: str,
        additional_context: dict[str, Any] | None = None,
    ) -> None:
        """Send a failure record to the DLQ for manual review."""
        if not DLQ_URL:
            logger.error("DLQ_URL not configured — failure record lost for request %s", request_id)
            return

        message = {
            "request_id": request_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "user_query_hash": _truncated_hash(user_query),
            "error_detail": error_detail[:1000],
            "context": additional_context or {},
        }
        try:
            self._sqs.send_message(
                QueueUrl=DLQ_URL,
                MessageBody=json.dumps(message),
                MessageGroupId="agent-failures",
                MessageDeduplicationId=request_id,
            )
            logger.info("Published failure record to DLQ for request %s", request_id)
        except Exception as exc:
            logger.error("Failed to publish to DLQ: %s", exc)

        self._emit_failure_metric()

    def _emit_failure_metric(self) -> None:
        try:
            self._cw.put_metric_data(
                Namespace="EnterpriseAssistant",
                MetricData=[{"MetricName": "UnrecoverableFailures", "Value": 1, "Unit": "Count"}],
            )
        except Exception as exc:
            logger.warning("CloudWatch metric emission failed: %s", exc)


def _truncated_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]
