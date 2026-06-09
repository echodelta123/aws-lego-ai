Here’s a toned-down, more natural rewrite with less heavy phrasing and reduced “platform brochure” tone while keeping the technical content intact.

---

# Project 3: ML Observability & Governance Framework

## Overview

This project provides monitoring and governance for both the recommendation system and the support agent. It focuses on tracking model health, data quality, and prompt behavior across the platform.

It covers two main areas:

* **Graph ML monitoring** — monitoring embeddings, predictions, and feature drift from the LightGCN recommendation model (Project 1)
* **LLM and prompt governance** — regression testing and validation of prompts used in the support system (Project 2)

It uses AWS-native tools like SageMaker Model Monitor, SageMaker Clarify, and CloudWatch, along with custom checks where needed.

Key responsibilities:

* Monitor model and data drift in production endpoints
* Run bias and fairness checks on recommendation outputs
* Validate prompt changes before they are deployed
* Generate audit-ready model documentation automatically

---

## Architecture

```
SageMaker Endpoint (Production)
        │
        ├── Data Capture → S3 (inference logs)
        │
        ├── Model Monitor Jobs
        │       ├── Data quality checks
        │       ├── Model quality checks
        │       └── Feature drift checks
        │
        ├── SageMaker Clarify (bias/fairness)
        │
        ▼
CloudWatch metrics and dashboards
        │
        ├── Alarms → SNS
        └── Lambda alert enrichment → Slack / PagerDuty


Prompt Governance Pipeline
        │
Git (prompt YAML files)
        │
CI: evaluate_prompt.py
        │
        ├── fail → reject change
        └── pass → S3 prompt registry (versioned)
```

---

## Key Files

| File                           | Purpose                                                     |
| ------------------------------ | ----------------------------------------------------------- |
| `src/monitor_setup.py`         | Configures SageMaker Model Monitor schedules                |
| `src/drift_detector.py`        | Custom drift detection logic (supplements SageMaker checks) |
| `src/alert_enricher.py`        | Adds context to alerts before sending to Slack/PagerDuty    |
| `src/bias_evaluator.py`        | Runs and parses SageMaker Clarify bias reports              |
| `src/model_card_generator.py`  | Generates model cards from SageMaker metadata               |
| `src/prompt_evaluator.py`      | Runs prompt regression tests in CI                          |
| `dashboards/model_health.json` | CloudWatch dashboard definition                             |
| `tests/test_drift_detector.py` | Tests for drift detection logic                             |
| `tests/test_bias_evaluator.py` | Tests for bias metric thresholds                            |

---

## LLM Observability (Langfuse)

LLM interactions and agent workflows are tracked using Langfuse:

* Each user interaction is recorded as a trace
* Captures prompts, retrieval steps, and response metadata
* Tracks latency and token usage per request
* Helps debug agent behavior across multi-step flows

---

## Monitored Metrics

| Category      | What it measures                              | Alert condition    |
| ------------- | --------------------------------------------- | ------------------ |
| Data quality  | Missing values, schema issues, invalid ranges | >2% violations     |
| Model quality | Accuracy, F1, AUC compared to baseline        | >5% drop           |
| Feature drift | Changes in embedding distributions (PSI)      | PSI > 0.2          |
| Data drift    | Input distribution shifts (KS test / PSI)     | PSI > 0.2          |
| Bias          | Disparate impact, fairness metrics            | DI < 0.8 or > 1.25 |
| Latency       | Endpoint response time (P95/P99)              | P99 > 500ms        |
| Errors        | 4xx/5xx rates                                 | >1% over 5 min     |
| Confidence    | Share of low-confidence responses             | >10%               |

---

## Setup

```bash id="7twf2m"
pip install -r requirements.txt
pytest tests/ -v

# Configure monitoring for a deployed endpoint
python src/monitor_setup.py \
  --endpoint-name my-model-endpoint \
  --baseline-data-uri s3://my-bucket/baselines/data-quality/

# Generate a model card
python src/model_card_generator.py \
  --model-package-arn arn:aws:sagemaker:eu-west-1:123456789:model-package/my-model/1

# Deploy monitoring stack
cd infra && cdk deploy ModelMonitoringStack
```

---

## Cost and Resource Design

The monitoring layer is designed to avoid always-on infrastructure:

* **SageMaker monitoring jobs run on demand** using short-lived ephemeral `ml.m5.large` compute instances. This ensures compute charges scale to zero immediately after the monitoring run completes.
* **CloudWatch and SNS are fully serverless**, with no idle cost
* **Bias and drift checks are scheduled**, not continuously running
* **Langfuse Cloud is used for dev workloads**, avoiding self-hosted infrastructure

---
