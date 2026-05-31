"""
pipeline/traceability_recorder.py
----------------------------------
Writes the SDLC traceability record to DynamoDB at deployment time.

This record is the single source of truth for answering:
  - What model version is running in production right now?
  - Who approved it, and when?
  - What data was it trained on?
  - What was its evaluation score?
  - Which Jira ticket triggered this change?

The record is write-once (immutable) — existing records are never overwritten,
only new records are written.  This guarantees the audit trail cannot be
retrospectively modified.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

TRACEABILITY_TABLE = os.environ.get("TRACEABILITY_TABLE_NAME", "ml-sdlc-traceability")


class TraceabilityRecorder:
    def __init__(self) -> None:
        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._table = dynamodb.Table(TRACEABILITY_TABLE)

    def record_deployment(
        self,
        *,
        endpoint_name: str,
        model_package_arn: str,
        model_version: str,
        git_commit_sha: str,
        jira_ticket: str,
        training_data_uri: str,
        evaluation_metrics: dict[str, float],
        approved_by: str,
        model_card_uri: str,
        deployment_config_name: str,
    ) -> str:
        """
        Write an immutable deployment traceability record.

        Returns the record_id of the written record.
        Raises ValueError if a record with the same model_package_arn already exists
        (guards against accidental duplicate deployment records).
        """
        record_id = self._make_record_id(endpoint_name, model_package_arn)

        # Check for duplicate (immutability guarantee)
        if self._record_exists(record_id):
            raise ValueError(
                f"Traceability record already exists for record_id={record_id}. "
                "Each model deployment must have a unique model_package_arn."
            )

        record = {
            "record_id": record_id,
            "endpoint_name": endpoint_name,
            "model_package_arn": model_package_arn,
            "model_version": model_version,
            "git_commit_sha": git_commit_sha,
            "jira_ticket": jira_ticket,
            "training_data_uri": training_data_uri,
            "evaluation_metrics": json.dumps(evaluation_metrics),
            "approved_by": approved_by,
            "model_card_uri": model_card_uri,
            "deployment_config_name": deployment_config_name,
            "deployed_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        # Conditional write — fails if record_id already exists (belt-and-braces)
        self._table.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(record_id)",
        )
        logger.info("Traceability record written: record_id=%s jira=%s", record_id, jira_ticket)
        return record_id

    def get_deployment_history(self, endpoint_name: str) -> list[dict[str, Any]]:
        """Return all traceability records for an endpoint, ordered by deployed_at_utc descending."""
        response = self._table.query(
            IndexName="endpoint-name-index",
            KeyConditionExpression=Key("endpoint_name").eq(endpoint_name),
            ScanIndexForward=False,  # newest first
        )
        return response.get("Items", [])

    def _record_exists(self, record_id: str) -> bool:
        response = self._table.get_item(
            Key={"record_id": record_id},
            ProjectionExpression="record_id",
        )
        return "Item" in response

    @staticmethod
    def _make_record_id(endpoint_name: str, model_package_arn: str) -> str:
        raw = f"{endpoint_name}::{model_package_arn}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
