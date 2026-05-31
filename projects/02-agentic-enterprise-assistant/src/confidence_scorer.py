"""
confidence_scorer.py
--------------------
Scores the confidence of a Bedrock Agent response before surfacing it to
the end user.

Low-confidence responses are escalated to a human review queue rather than
being returned directly.  This prevents plausible-sounding but incorrect
responses from reaching users — especially important in enterprise contexts
where a wrong answer can have real operational or legal consequences.

Scoring approach:
  The scorer makes a secondary Bedrock call asking the model to self-evaluate
  its own response against the retrieved context.  This is a lightweight but
  effective "LLM-as-judge" pattern.

  Threshold: responses below 0.75 confidence are escalated.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import boto3

logger = logging.getLogger(__name__)

SCORER_MODEL_ID = "anthropic.claude-haiku-20240307-v1:0"
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.75"))


@dataclass
class ScoringResult:
    score: float          # 0.0 – 1.0
    requires_escalation: bool
    reasoning: str


class ConfidenceScorer:
    def __init__(self) -> None:
        self._bedrock = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "eu-west-1"),
        )

    def score(self, user_query: str, agent_response: str, retrieved_context: str) -> ScoringResult:
        """
        Ask a secondary model to evaluate how well the agent_response is
        grounded in the retrieved_context relative to the user_query.

        Returns a ScoringResult; on scorer failure, returns a conservative
        escalation (fail-safe behaviour).
        """
        prompt = self._build_scoring_prompt(user_query, agent_response, retrieved_context)

        try:
            raw = self._invoke_scorer(prompt)
            parsed = json.loads(raw)
            score = float(parsed["confidence_score"])
            score = max(0.0, min(1.0, score))  # clamp to [0, 1]
            return ScoringResult(
                score=score,
                requires_escalation=score < CONFIDENCE_THRESHOLD,
                reasoning=str(parsed.get("reasoning", "")),
            )
        except Exception as exc:
            logger.error("Confidence scorer failed: %s — escalating as fail-safe", exc)
            return ScoringResult(
                score=0.0,
                requires_escalation=True,
                reasoning=f"Scorer unavailable: {exc}",
            )

    def _invoke_scorer(self, prompt: str) -> str:
        response = self._bedrock.invoke_model(
            modelId=SCORER_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        parsed = json.loads(response["body"].read())
        return parsed["content"][0]["text"]

    def _build_scoring_prompt(
        self, user_query: str, agent_response: str, retrieved_context: str
    ) -> str:
        return (
            "You are evaluating whether an AI assistant response is well-grounded "
            "in the provided context and correctly answers the user's question.\n\n"
            f"USER QUESTION: {user_query}\n\n"
            f"RETRIEVED CONTEXT (ground truth):\n{retrieved_context[:2000]}\n\n"
            f"AI RESPONSE:\n{agent_response[:1000]}\n\n"
            "Rate the confidence that the AI response is factually correct and grounded "
            "in the retrieved context. Use a score from 0.0 (completely wrong/hallucinated) "
            "to 1.0 (perfectly correct and grounded).\n\n"
            "Respond ONLY with JSON: "
            "{\"confidence_score\": <0.0-1.0>, \"reasoning\": \"brief explanation\"}"
        )
