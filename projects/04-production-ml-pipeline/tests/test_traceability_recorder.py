"""
tests/test_traceability_recorder.py
------------------------------------
Unit tests for the SDLC traceability recorder.
Uses moto to mock DynamoDB — no real AWS calls needed.
"""

from __future__ import annotations

import os
import pytest
import boto3
from moto import mock_aws

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../pipeline"))

# Set dummy AWS creds for moto
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ["TRACEABILITY_TABLE_NAME"] = "ml-sdlc-traceability"

from traceability_recorder import TraceabilityRecorder

SAMPLE_ARGS = {
    "endpoint_name": "my-model-prod",
    "model_package_arn": "arn:aws:sagemaker:eu-west-1:123456789:model-package/my-model/7",
    "model_version": "7",
    "git_commit_sha": "a3f9e21",
    "jira_ticket": "AI-247",
    "training_data_uri": "s3://data/features/v2024-11-01/",
    "evaluation_metrics": {"accuracy": 0.943, "f1": 0.921},
    "approved_by": "john.smith@company.com",
    "model_card_uri": "s3://governance/model-cards/my-model/v7/model_card.md",
    "deployment_config_name": "my-model-config-v7",
}


@pytest.fixture
def recorder():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")
        table = dynamodb.create_table(
            TableName="ml-sdlc-traceability",
            KeySchema=[{"AttributeName": "record_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "record_id", "AttributeType": "S"},
                {"AttributeName": "endpoint_name", "AttributeType": "S"},
                {"AttributeName": "deployed_at_utc", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "endpoint-name-index",
                "KeySchema": [
                    {"AttributeName": "endpoint_name", "KeyType": "HASH"},
                    {"AttributeName": "deployed_at_utc", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        yield TraceabilityRecorder()


def test_record_deployment_writes_record(recorder):
    record_id = recorder.record_deployment(**SAMPLE_ARGS)
    assert isinstance(record_id, str) and len(record_id) == 32


def test_duplicate_deployment_raises(recorder):
    recorder.record_deployment(**SAMPLE_ARGS)
    with pytest.raises(Exception):
        recorder.record_deployment(**SAMPLE_ARGS)


def test_record_id_is_deterministic():
    id1 = TraceabilityRecorder._make_record_id("ep", "arn:123")
    id2 = TraceabilityRecorder._make_record_id("ep", "arn:123")
    assert id1 == id2


def test_different_arns_produce_different_ids():
    id1 = TraceabilityRecorder._make_record_id("ep", "arn:v1")
    id2 = TraceabilityRecorder._make_record_id("ep", "arn:v2")
    assert id1 != id2


def test_get_deployment_history_returns_records(recorder):
    recorder.record_deployment(**SAMPLE_ARGS)
    history = recorder.get_deployment_history("my-model-prod")
    assert len(history) >= 1
    assert history[0]["jira_ticket"] == "AI-247"

