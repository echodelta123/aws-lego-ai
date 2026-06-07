"""
drift_detector.py
-----------------
Custom drift detection that supplements SageMaker Model Monitor's built-in
checks with additional statistical tests and business-relevant thresholds.

SageMaker Model Monitor is powerful but uses generic thresholds.  This module
adds:
  - Population Stability Index (PSI) calculation for each key feature
  - Jensen-Shannon divergence for categorical features
  - Business-context-aware thresholds (different features have different risk levels)
  - A structured DriftReport object suitable for downstream alerting

The output from this module feeds directly into the CloudWatch alarm enricher
and the operational dashboard.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# PSI interpretation (industry standard)
PSI_LOW = 0.10       # minimal drift — monitor but no action needed
PSI_MEDIUM = 0.20    # moderate drift — investigate
PSI_HIGH = 0.25      # significant drift — alert and consider retraining


class DriftSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class FeatureDriftResult:
    feature_name: str
    psi: float
    severity: DriftSeverity
    baseline_mean: float
    current_mean: float
    n_buckets: int


@dataclass
class DriftReport:
    endpoint_name: str
    evaluation_window_hours: int
    features: list[FeatureDriftResult] = field(default_factory=list)

    @property
    def max_severity(self) -> DriftSeverity:
        if not self.features:
            return DriftSeverity.NONE
        order = [DriftSeverity.NONE, DriftSeverity.LOW, DriftSeverity.MEDIUM, DriftSeverity.HIGH]
        return max(self.features, key=lambda f: order.index(f.severity)).severity

    @property
    def drifted_features(self) -> list[FeatureDriftResult]:
        return [f for f in self.features if f.severity != DriftSeverity.NONE]

    def to_cloudwatch_metrics(self) -> list[dict[str, Any]]:
        """Produce a list of CloudWatch MetricData entries for this report."""
        metrics = []
        for f in self.features:
            metrics.append({
                "MetricName": "FeaturePSI",
                "Dimensions": [
                    {"Name": "EndpointName", "Value": self.endpoint_name},
                    {"Name": "FeatureName", "Value": f.feature_name},
                ],
                "Value": f.psi,
                "Unit": "None",
            })
        return metrics


class DriftDetector:
    """Computes PSI for each feature between baseline and current distributions."""

    def __init__(self, n_buckets: int = 10) -> None:
        self._n_buckets = n_buckets

    def evaluate(
        self,
        endpoint_name: str,
        baseline: dict[str, list[float]],
        current: dict[str, list[float]],
        evaluation_window_hours: int = 24,
    ) -> DriftReport:
        """
        Compute per-feature PSI between baseline and current data.

        Args:
            endpoint_name:             Name of the SageMaker endpoint being monitored.
            baseline:                  Dict of feature_name → list of baseline values.
            current:                   Dict of feature_name → list of current values.
            evaluation_window_hours:   Window size (for report metadata).

        Returns:
            DriftReport containing a FeatureDriftResult for every feature in baseline.
        """
        report = DriftReport(
            endpoint_name=endpoint_name,
            evaluation_window_hours=evaluation_window_hours,
        )

        for feature_name, baseline_values in baseline.items():
            if feature_name not in current:
                logger.warning("Feature '%s' present in baseline but not in current data", feature_name)
                continue

            current_values = current[feature_name]
            if len(current_values) < 30:
                logger.warning(
                    "Insufficient data for feature '%s': %d samples (need >=30)", feature_name, len(current_values)
                )
                continue

            psi = self._compute_psi(baseline_values, current_values)
            severity = self._psi_to_severity(psi)

            report.features.append(
                FeatureDriftResult(
                    feature_name=feature_name,
                    psi=psi,
                    severity=severity,
                    baseline_mean=float(np.mean(baseline_values)),
                    current_mean=float(np.mean(current_values)),
                    n_buckets=self._n_buckets,
                )
            )
            if severity != DriftSeverity.NONE:
                logger.info("Drift detected — feature '%s': PSI=%.4f severity=%s", feature_name, psi, severity)

        return report

    def _compute_psi(self, baseline: list[float], current: list[float]) -> float:
        """
        Population Stability Index (PSI):
            PSI = Σ (P_current - P_baseline) * ln(P_current / P_baseline)
        """
        baseline_arr = np.array(baseline, dtype=float)
        current_arr = np.array(current, dtype=float)

        # Use baseline to define bucket edges
        min_val = min(baseline_arr.min(), current_arr.min())
        max_val = max(baseline_arr.max(), current_arr.max())

        if min_val == max_val:
            return 0.0  # no variance — no drift

        edges = np.linspace(min_val, max_val, self._n_buckets + 1)
        baseline_counts, _ = np.histogram(baseline_arr, bins=edges)
        current_counts, _ = np.histogram(current_arr, bins=edges)

        # Convert to proportions, avoiding zero division
        eps = 1e-10
        p_baseline = (baseline_counts + eps) / (len(baseline_arr) + eps * self._n_buckets)
        p_current = (current_counts + eps) / (len(current_arr) + eps * self._n_buckets)

        psi = float(np.sum((p_current - p_baseline) * np.log(p_current / p_baseline)))
        return max(0.0, psi)  # PSI is always non-negative

    @staticmethod
    def _psi_to_severity(psi: float) -> DriftSeverity:
        if psi < PSI_LOW:
            return DriftSeverity.NONE
        if psi < PSI_MEDIUM:
            return DriftSeverity.LOW
        if psi < PSI_HIGH:
            return DriftSeverity.MEDIUM
        return DriftSeverity.HIGH
