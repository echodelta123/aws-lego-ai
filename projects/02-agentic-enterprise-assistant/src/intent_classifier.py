"""
intent_classifier.py
--------------------
Classifies the risk level of an incoming user request BEFORE the Bedrock Agent
acts on it.  This is the high-risk decision boundary layer.

Risk levels:
  LOW      — safe to proceed autonomously
  MEDIUM   — proceed, but log with enhanced audit detail
  HIGH     — route to human approval queue; do NOT invoke agent
  BLOCKED  — reject immediately; alert security team

The classifier uses a combination of:
  1. Keyword/pattern matching (fast, deterministic — catches obvious cases)
  2. A lightweight Bedrock call (Claude Haiku) for ambiguous cases

This two-step approach means obvious bad requests never even reach a model.
"""

from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum
from typing import NamedTuple

import boto3

logger = logging.getLogger(__name__)

CLASSIFIER_MODEL_ID = "anthropic.claude-haiku-20240307-v1:0"

# Patterns that always result in BLOCKED — no model call needed
BLOCKED_PATTERNS = [
    re.compile(r"\bpassword\b", re.IGNORECASE),
    re.compile(r"\bsecret[_\s]?key\b", re.IGNORECASE),
    re.compile(r"\biam\s+role\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"ignore\s+(previous|above|all)\s+instructions", re.IGNORECASE),
    re.compile(r"\bsocial\s+security\b", re.IGNORECASE),
]

# Patterns that always result in HIGH risk routing
HIGH_RISK_PATTERNS = [
    re.compile(r"\bdelete\b.*(production|prod|live|database|db)", re.IGNORECASE),
    re.compile(r"\bdeploy\b.*(production|prod)", re.IGNORECASE),
    re.compile(r"\btransfer\b.*\b(funds?|money|payment)\b", re.IGNORECASE),
    re.compile(r"\bpatch\b.*(firewall|security\s+group|vpc)", re.IGNORECASE),
]


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


class ClassificationResult(NamedTuple):
    risk_level: RiskLevel
    reason: str
    used_model: bool


class IntentClassifier:
    def __init__(self) -> None:
        self._bedrock = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "eu-west-1"),
        )

    def classify(self, user_input: str) -> ClassificationResult:
        """
        Classify the risk level of a user request.

        Fast-path pattern matching runs first.  Only ambiguous requests
        proceed to a model call.
        """
        # Step 1: deterministic keyword checks
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(user_input):
                return ClassificationResult(
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"Matched blocked pattern: {pattern.pattern}",
                    used_model=False,
                )

        for pattern in HIGH_RISK_PATTERNS:
            if pattern.search(user_input):
                return ClassificationResult(
                    risk_level=RiskLevel.HIGH,
                    reason=f"Matched high-risk pattern: {pattern.pattern}",
                    used_model=False,
                )

        # Step 2: model-based classification for ambiguous inputs
        return self._model_classify(user_input)

    def _model_classify(self, user_input: str) -> ClassificationResult:
        """Use Claude Haiku to classify ambiguous requests."""
        prompt = (
            "You are a risk classifier for an enterprise AI assistant. "
            "Classify the following user request as one of: LOW, MEDIUM, HIGH.\n"
            "LOW = information retrieval or summarisation only.\n"
            "MEDIUM = creates, updates or sends data.\n"
            "HIGH = financial transactions, system/infrastructure changes, or legal decisions.\n"
            "Respond with ONLY a JSON object: {\"risk_level\": \"LOW|MEDIUM|HIGH\", \"reason\": \"brief reason\"}\n\n"
            f"User request: {user_input}"
        )
        try:
            response = self._bedrock.invoke_model(
                modelId=CLASSIFIER_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}],
                }),
            )
            parsed = json.loads(response["body"].read())
            text = parsed["content"][0]["text"]
            result = json.loads(text)
            return ClassificationResult(
                risk_level=RiskLevel(result["risk_level"]),
                reason=result.get("reason", "model classified"),
                used_model=True,
            )
        except Exception as exc:
            # Fail safe: if classifier is unavailable, treat as HIGH
            logger.error("Intent classifier model call failed: %s — defaulting to HIGH", exc)
            return ClassificationResult(
                risk_level=RiskLevel.HIGH,
                reason=f"Classifier unavailable: {exc}",
                used_model=False,
            )
