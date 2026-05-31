"""
tests/test_confidence_scorer.py
--------------------------------
Tests for the confidence scoring and escalation logic.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from confidence_scorer import ConfidenceScorer


def _make_scorer(score_value: float) -> ConfidenceScorer:
    scorer = ConfidenceScorer.__new__(ConfidenceScorer)
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(
            read=lambda: json.dumps({
                "content": [{"text": json.dumps({"confidence_score": score_value, "reasoning": "test"})}]
            }).encode()
        )
    }
    scorer._bedrock = mock_bedrock
    return scorer


class TestConfidenceScorer:
    def test_high_confidence_does_not_escalate(self):
        scorer = _make_scorer(0.90)
        result = scorer.score("What is our refund policy?", "The refund policy is 30 days.", "context...")
        assert result.score == pytest.approx(0.90)
        assert result.requires_escalation is False

    def test_low_confidence_triggers_escalation(self):
        scorer = _make_scorer(0.50)
        result = scorer.score("What is our refund policy?", "I'm not sure but maybe 7 days?", "context...")
        assert result.score == pytest.approx(0.50)
        assert result.requires_escalation is True

    def test_boundary_at_threshold_does_not_escalate(self):
        """Score exactly at 0.75 should NOT require escalation."""
        scorer = _make_scorer(0.75)
        result = scorer.score("query", "response", "context")
        assert result.requires_escalation is False

    def test_just_below_threshold_escalates(self):
        scorer = _make_scorer(0.74)
        result = scorer.score("query", "response", "context")
        assert result.requires_escalation is True

    def test_score_clamped_above_1(self):
        scorer = _make_scorer(1.5)  # model returned out-of-range value
        result = scorer.score("q", "r", "c")
        assert result.score == pytest.approx(1.0)

    def test_score_clamped_below_0(self):
        scorer = _make_scorer(-0.3)
        result = scorer.score("q", "r", "c")
        assert result.score == pytest.approx(0.0)
        assert result.requires_escalation is True

    def test_scorer_failure_escalates_as_fail_safe(self):
        scorer = ConfidenceScorer.__new__(ConfidenceScorer)
        scorer._bedrock = MagicMock()
        scorer._bedrock.invoke_model.side_effect = Exception("Bedrock down")
        result = scorer.score("query", "response", "context")
        assert result.requires_escalation is True
        assert result.score == pytest.approx(0.0)
