"""
tests/test_drift_detector.py
-----------------------------
Unit tests for the PSI-based drift detector.
No AWS calls needed — this is pure numerical logic.
"""

from __future__ import annotations

import pytest
import numpy as np

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from drift_detector import DriftDetector, DriftSeverity, DriftReport


class TestPSIComputation:
    def setup_method(self):
        self.detector = DriftDetector(n_buckets=10)

    def test_identical_distributions_have_zero_psi(self):
        data = list(np.random.normal(0, 1, 500))
        psi = self.detector._compute_psi(data, data)
        assert psi == pytest.approx(0.0, abs=1e-9)

    def test_severely_different_distributions_have_high_psi(self):
        baseline = list(np.random.normal(0, 1, 1000))
        current = list(np.random.normal(10, 1, 1000))  # completely different mean
        psi = self.detector._compute_psi(baseline, current)
        assert psi > 0.25  # should be HIGH severity

    def test_psi_is_always_non_negative(self):
        for _ in range(20):
            a = list(np.random.normal(0, 1, 200))
            b = list(np.random.normal(0.5, 1.2, 200))
            assert self.detector._compute_psi(a, b) >= 0.0

    def test_constant_feature_returns_zero(self):
        baseline = [5.0] * 100
        current = [5.0] * 100
        psi = self.detector._compute_psi(baseline, current)
        assert psi == pytest.approx(0.0)


class TestSeverityClassification:
    def test_psi_below_0_10_is_none(self):
        assert DriftDetector._psi_to_severity(0.05) == DriftSeverity.NONE

    def test_psi_0_10_is_low(self):
        assert DriftDetector._psi_to_severity(0.10) == DriftSeverity.LOW

    def test_psi_0_20_is_medium(self):
        assert DriftDetector._psi_to_severity(0.20) == DriftSeverity.MEDIUM

    def test_psi_above_0_25_is_high(self):
        assert DriftDetector._psi_to_severity(0.30) == DriftSeverity.HIGH


class TestDriftReport:
    def _make_report(self, severities: list[str]) -> DriftReport:
        from drift_detector import FeatureDriftResult
        report = DriftReport(endpoint_name="test-endpoint", evaluation_window_hours=24)
        for i, sev in enumerate(severities):
            report.features.append(
                FeatureDriftResult(
                    feature_name=f"feature_{i}",
                    psi=0.1 * i,
                    severity=DriftSeverity(sev),
                    baseline_mean=0.0,
                    current_mean=0.1 * i,
                    n_buckets=10,
                )
            )
        return report

    def test_max_severity_returns_highest(self):
        report = self._make_report(["NONE", "LOW", "HIGH", "MEDIUM"])
        assert report.max_severity == DriftSeverity.HIGH

    def test_drifted_features_excludes_none(self):
        report = self._make_report(["NONE", "LOW", "NONE"])
        assert len(report.drifted_features) == 1
        assert report.drifted_features[0].severity == DriftSeverity.LOW

    def test_empty_report_has_none_severity(self):
        report = DriftReport(endpoint_name="test", evaluation_window_hours=1)
        assert report.max_severity == DriftSeverity.NONE

    def test_cloudwatch_metrics_format(self):
        report = self._make_report(["LOW", "MEDIUM"])
        metrics = report.to_cloudwatch_metrics()
        assert len(metrics) == 2
        assert all(m["MetricName"] == "FeaturePSI" for m in metrics)
        assert all(m["Unit"] == "None" for m in metrics)


class TestEvaluateMethod:
    def test_missing_current_feature_is_skipped(self):
        detector = DriftDetector()
        baseline = {"feat_a": list(np.random.normal(0, 1, 100))}
        current = {}  # feat_a missing from current
        report = detector.evaluate("ep", baseline, current)
        assert len(report.features) == 0

    def test_insufficient_current_data_is_skipped(self):
        detector = DriftDetector()
        baseline = {"feat_a": list(np.random.normal(0, 1, 100))}
        current = {"feat_a": [1.0, 2.0]}  # only 2 samples
        report = detector.evaluate("ep", baseline, current)
        assert len(report.features) == 0

    def test_full_evaluation_produces_results(self):
        rng = np.random.default_rng(seed=42)  # fixed seed for determinism
        detector = DriftDetector()
        # Use very large samples so PSI is reliably near-zero for identical distributions
        baseline = {"feat_a": list(rng.normal(0, 1, 5000))}
        current = {"feat_a": list(rng.normal(0, 1, 5000))}
        report = detector.evaluate("ep", baseline, current)
        assert len(report.features) == 1
        assert report.features[0].feature_name == "feat_a"
        # PSI between two large same-distribution samples must be well below 0.10
        assert report.features[0].psi < 0.05
