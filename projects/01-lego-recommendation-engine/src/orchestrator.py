"""
orchestrator.py
---------------
Lambda entrypoint for the LEGO AI Recommendation Engine.

Responsibilities:
- Validate and sanitise incoming requests
- Invoke the Bedrock Agent and capture structured responses
- Route behavioural events to Kinesis
- Delegate audit logging to audit_logger
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import boto3
from pydantic import BaseModel, Field, ValidationError

from audit_logger import AuditLogger
from behaviour_tracker import BehaviourTracker
from guardrails import HallucinationGuard
from recommendation_model import RecommendationClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AGENT_ID = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS_ID = os.environ["BEDROCK_AGENT_ALIAS_ID"]

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
audit = AuditLogger()
behaviour = BehaviourTracker()
guard = HallucinationGuard()
rec_client = RecommendationClient()


class RecommendationRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    query: str = Field(..., min_length=3, max_length=500)
    age_group: str | None = Field(default=None, pattern=r"^(3-5|6-9|10-12|13-17|18\+)$")
    max_results: int = Field(default=5, ge=1, le=20)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = str(uuid.uuid4())

    # Parse and validate the incoming request body
    try:
        body = json.loads(event.get("body") or "{}")
        req = RecommendationRequest(**body)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Invalid request body: %s", exc)
        return _response(400, {"error": "Invalid request", "detail": str(exc)})

    logger.info("Processing recommendation request %s for customer %s", request_id, req.customer_id)

    # Invoke the Bedrock Agent with a structured session
    try:
        agent_response = _invoke_agent(req, request_id)
    except Exception as exc:
        logger.error("Bedrock Agent invocation failed for request %s: %s", request_id, exc)
        audit.record_failure(request_id, req.customer_id, str(exc))
        return _response(502, {"error": "Recommendation service temporarily unavailable"})

    # Validate agent output against live catalogue (hallucination guard)
    validated = guard.validate(agent_response["recommendations"])
    if not validated["passed"]:
        logger.warning("Hallucination guard triggered for request %s: %s", request_id, validated["removed"])
        agent_response["recommendations"] = validated["safe_items"]
        agent_response["guardrail_triggered"] = True

    # Track behaviour event
    behaviour.publish(
        customer_id=req.customer_id,
        event_type="recommendation_served",
        payload={"query": req.query, "num_results": len(agent_response["recommendations"])},
    )

    # Write audit record
    audit.record_success(request_id, req.customer_id, req.query, agent_response)

    return _response(200, {"request_id": request_id, **agent_response})


def _invoke_agent(req: RecommendationRequest, request_id: str) -> dict[str, Any]:
    """Invoke the Bedrock Agent and aggregate the streamed response."""
    input_text = _build_agent_input(req)

    response = bedrock_agent_runtime.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=f"{req.customer_id}-{request_id}",
        inputText=input_text,
    )

    # Bedrock Agent returns a streaming EventStream — collect completion chunks
    completion = ""
    for event in response.get("completion", []):
        chunk = event.get("chunk", {})
        completion += chunk.get("bytes", b"").decode("utf-8")

    # The agent is prompted to return structured JSON — parse and validate
    try:
        parsed = json.loads(completion)
    except json.JSONDecodeError:
        raise ValueError(f"Agent returned non-JSON response: {completion[:200]}")

    if "recommendations" not in parsed:
        raise ValueError(f"Agent response missing 'recommendations' key: {parsed.keys()}")

    return parsed


def _build_agent_input(req: RecommendationRequest) -> str:
    parts = [f"Find LEGO product recommendations for: {req.query}"]
    if req.age_group:
        parts.append(f"Target age group: {req.age_group}")
    parts.append(f"Return up to {req.max_results} results.")
    parts.append("Respond ONLY with valid JSON matching the schema: {\"recommendations\": [{\"product_id\": str, \"name\": str, \"reason\": str, \"price_gbp\": float}]}")
    return " ".join(parts)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
