"""
tests/test_recommendation_model.py
-----------------------------------
Unit tests for the SageMaker inference wrapper.
AWS calls are mocked so no real endpoint is required.
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from recommendation_model import InferenceInput, RecommendationClient


def _make_client(endpoint_response: dict) -> RecommendationClient:
    client = RecommendationClient.__new__(RecommendationClient)
    mock_sm = MagicMock()
    mock_sm.invoke_endpoint.return_value = {
        "Body": BytesIO(json.dumps(endpoint_response).encode()),
    }
    client._client = mock_sm
    return client


class TestInferenceInput:
    def test_valid_input(self):
        inp = InferenceInput(customer_id="cust-1", candidate_product_ids=["P1", "P2"], top_k=5)
        assert inp.top_k == 5

    def test_empty_product_ids_rejected(self):
        with pytest.raises(Exception):
            InferenceInput(customer_id="cust-1", candidate_product_ids=[])

    def test_empty_string_in_ids_rejected(self):
        with pytest.raises(Exception):
            InferenceInput(customer_id="cust-1", candidate_product_ids=["P1", ""])


class TestRecommendationClient:
    def test_successful_inference(self):
        fake_response = {
            "ranked_products": [
                {"product_id": "PROD-001", "score": 0.95},
                {"product_id": "PROD-002", "score": 0.87},
            ],
            "model_version": "1.3.0",
        }
        client = _make_client(fake_response)
        inp = InferenceInput(customer_id="cust-1", candidate_product_ids=["PROD-001", "PROD-002"])
        result = client.predict(inp)

        assert result.customer_id == "cust-1"
        assert len(result.ranked_products) == 2
        assert result.ranked_products[0].product_id == "PROD-001"
        assert result.ranked_products[0].rank == 1
        assert result.model_version == "1.3.0"

    def test_non_json_response_raises(self):
        client = RecommendationClient.__new__(RecommendationClient)
        mock_sm = MagicMock()
        mock_sm.invoke_endpoint.return_value = {"Body": BytesIO(b"not json")}
        client._client = mock_sm
        inp = InferenceInput(customer_id="c", candidate_product_ids=["P1"])
        with pytest.raises(ValueError, match="non-JSON"):
            client.predict(inp)

    def test_missing_ranked_products_key_raises(self):
        client = _make_client({"something_else": []})
        inp = InferenceInput(customer_id="c", candidate_product_ids=["P1"])
        with pytest.raises(ValueError, match="ranked_products"):
            client.predict(inp)

    def test_malformed_product_entry_raises(self):
        client = _make_client({"ranked_products": [{"no_id_here": 0.5}]})
        inp = InferenceInput(customer_id="c", candidate_product_ids=["P1"])
        with pytest.raises(ValueError, match="Malformed"):
            client.predict(inp)

    def test_endpoint_error_raises_runtime_error(self):
        client = RecommendationClient.__new__(RecommendationClient)
        mock_sm = MagicMock()
        mock_sm.invoke_endpoint.side_effect = Exception("Endpoint not found")
        client._client = mock_sm
        inp = InferenceInput(customer_id="c", candidate_product_ids=["P1"])
        with pytest.raises(RuntimeError, match="unavailable"):
            client.predict(inp)
