"""
recommendation_model.py
-----------------------
Thin wrapper around the SageMaker real-time inference endpoint for
collaborative-filtering based LEGO product recommendations.

Responsibilities:
  - Enforce input schema before sending to the endpoint
  - Parse and validate the endpoint's response
  - Record inference latency for CloudWatch metrics
  - Surface a typed result object — no raw dicts escape this module
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import boto3
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "lego-collab-filter-endpoint")


class InferenceInput(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=64)
    candidate_product_ids: list[str] = Field(..., min_length=1, max_length=100)
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("candidate_product_ids")
    @classmethod
    def no_empty_ids(cls, v: list[str]) -> list[str]:
        if any(not pid.strip() for pid in v):
            raise ValueError("candidate_product_ids must not contain empty strings")
        return v


@dataclass
class RankedProduct:
    product_id: str
    score: float
    rank: int


@dataclass
class InferenceResult:
    customer_id: str
    ranked_products: list[RankedProduct] = field(default_factory=list)
    model_version: str = ""
    latency_ms: float = 0.0


class RecommendationClient:
    """Calls the SageMaker endpoint and wraps results in typed objects."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "sagemaker-runtime",
            region_name=os.environ.get("AWS_REGION", "eu-west-1"),
        )

    def predict(self, input_data: InferenceInput) -> InferenceResult:
        """
        Send a validated inference request and return a typed InferenceResult.
        Raises ValueError on malformed responses; raises RuntimeError on endpoint errors.
        """
        payload = input_data.model_dump_json()

        start = time.monotonic()
        try:
            response = self._client.invoke_endpoint(
                EndpointName=ENDPOINT_NAME,
                ContentType="application/json",
                Accept="application/json",
                Body=payload,
            )
        except Exception as exc:
            logger.error("SageMaker endpoint invocation failed: %s", exc)
            raise RuntimeError(f"Endpoint unavailable: {exc}") from exc
        finally:
            latency_ms = (time.monotonic() - start) * 1000

        raw_body = response["Body"].read()
        try:
            parsed: dict[str, Any] = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Endpoint returned non-JSON response: {raw_body[:200]}") from exc

        return self._parse_response(input_data.customer_id, parsed, latency_ms)

    def _parse_response(
        self, customer_id: str, parsed: dict[str, Any], latency_ms: float
    ) -> InferenceResult:
        ranked_raw = parsed.get("ranked_products")
        if not isinstance(ranked_raw, list):
            raise ValueError(f"Expected 'ranked_products' list in response, got: {type(ranked_raw)}")

        ranked = []
        for i, item in enumerate(ranked_raw):
            if "product_id" not in item or "score" not in item:
                raise ValueError(f"Malformed ranked product at index {i}: {item}")
            ranked.append(
                RankedProduct(
                    product_id=str(item["product_id"]),
                    score=float(item["score"]),
                    rank=i + 1,
                )
            )

        return InferenceResult(
            customer_id=customer_id,
            ranked_products=ranked,
            model_version=str(parsed.get("model_version", "unknown")),
            latency_ms=latency_ms,
        )
