# Project 3: ML Monitoring & Governance Framework

## What This Project Shows

Production AI systems degrade silently unless you're actively watching them.  This framework provides continuous monitoring of **model health**, **data drift**, **output quality**, and **bias metrics** — with automated alerting and an audit-ready prompt versioning system.

This project is the direct answer to these job description requirements:
- *"Implementing ML monitoring frameworks (drift detection, model health, quality metrics)"*
- *"Support prompt governance, including documentation of prompt structures, versioning, constraints"*
- *"Execute structured model testing, performance evaluation, and safety/bias checks"*

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Monitoring Pipeline                                               │
│                                                                    │
│  SageMaker Endpoint (production)                                   │
│      │                                                             │
│      ├─► Data Capture Config ──► S3 (captured I/O)                │
│      │                               │                            │
│      │                    ┌──────────┴─────────────┐              │
│      │                    ▼                         ▼              │
│      │          Model Monitor Jobs           Clarify Job           │
│      │          ┌──────────────────┐        (bias/fairness)        │
│      │          │ DataQuality      │                               │
│      │          │ ModelQuality     │                               │
│      │          │ FeatureAttrib    │                               │
│      │          └────────┬─────────┘                              │
│      │                   │ CloudWatch metrics                     │
│      │                   ▼                                        │
│      │          CloudWatch Dashboard                              │
│      │          CloudWatch Alarms ──► SNS ──► Lambda Enricher     │
│      │                                            │               │
│      │                                     Slack / PagerDuty      │
│      │                                                             │
│  Prompt Governance Pipeline                                        │
│      │                                                             │
│  Git repo (YAML prompt drafts)                                     │
│      │                                                             │
│  evaluate_prompt.py (CI)                                           │
│      │ PASS                                                        │
│      ▼                                                             │
│  S3 Prompt Registry (versioned, immutable)                         │
└────────────────────────────────────────────────────────────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/monitor_setup.py` | Creates/updates SageMaker Model Monitor schedules for all monitor types |
| `src/drift_detector.py` | Custom drift detection logic supplementing SageMaker's built-in checks |
| `src/alert_enricher.py` | Lambda that adds context to CloudWatch alarms before routing to Slack/PagerDuty |
| `src/bias_evaluator.py` | Schedules Clarify bias evaluation jobs and parses results |
| `src/model_card_generator.py` | Auto-generates standardised model cards from SageMaker metadata |
| `src/prompt_evaluator.py` | CI-runnable script: tests a prompt version against its golden test suite |
| `dashboards/model_health.json` | CloudWatch dashboard definition (deployable via CDK) |
| `tests/test_drift_detector.py` | Unit tests for drift thresholds and alerting logic |
| `tests/test_bias_evaluator.py` | Unit tests for bias metric parsing and threshold enforcement |

---

## Monitored Metrics

| Metric Category | What's Measured | Alert Threshold |
|----------------|-----------------|-----------------|
| Data Quality | Feature null rates, schema violations, out-of-range values | >2% violation rate |
| Model Quality | Prediction accuracy, F1, AUC vs. baseline | >5% degradation |
| Feature Attribution Drift | SHAP value drift from baseline | PSI > 0.2 |
| Data Drift | Input distribution shift (KS test, PSI) | PSI > 0.2 |
| Bias / Fairness | Disparate impact, equal opportunity difference | DI < 0.8 or > 1.25 |
| Latency | P50/P95/P99 endpoint latency | P99 > 500ms |
| Error Rate | 4xx/5xx responses from endpoint | >1% over 5 min |
| Confidence Distribution | % of responses below confidence threshold | >10% low-confidence |

---

## Setup

```bash
pip install -r requirements.txt
python -m pytest tests/ -v

# Set up monitors for a deployed endpoint
python src/monitor_setup.py \
  --endpoint-name my-model-endpoint \
  --baseline-data-uri s3://my-bucket/baselines/data-quality/

# Generate a model card
python src/model_card_generator.py \
  --model-package-arn arn:aws:sagemaker:eu-west-1:123456789:model-package/my-model/1

# Deploy monitoring infrastructure
cd infra && cdk deploy ModelMonitoringStack
```
