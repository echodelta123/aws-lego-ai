"""
behaviour_tracker.py
--------------------
Publishes customer behaviour events to a Kinesis Data Stream.

Events are schema-validated before publishing.  The stream feeds into
Kinesis Firehose → S3 → Glue → SageMaker Feature Store, so data quality
at the point of capture is critical — garbage in causes model drift.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

import boto3
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

STREAM_NAME = os.environ.get("BEHAVIOUR_STREAM_NAME", "lego-customer-behaviour")

EventType = Literal[
    "recommendation_served",
    "product_viewed",
    "product_added_to_cart",
    "product_purchased",
    "search_performed",
    "recommendation_clicked",
]


class BehaviourEvent(BaseModel):
    event_id: str
    customer_id: str = Field(..., min_length=1, max_length=64)
    event_type: EventType
    timestamp_utc: str
    payload: dict[str, Any]
    schema_version: str = "1.0"


class BehaviourTracker:
    def __init__(self) -> None:
        self._kinesis = boto3.client("kinesis", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def publish(self, customer_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        """Validate and publish a behaviour event to Kinesis."""
        import uuid

        event = BehaviourEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            event_type=event_type,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            payload=payload,
        )
        try:
            self._kinesis.put_record(
                StreamName=STREAM_NAME,
                Data=event.model_dump_json().encode("utf-8"),
                PartitionKey=customer_id,  # partition by customer for ordered events
            )
            logger.debug("Published behaviour event %s for customer %s", event.event_id, customer_id)
        except Exception as exc:
            # Non-critical: log and continue — don't fail the recommendation call
            logger.error("Failed to publish behaviour event: %s", exc)
