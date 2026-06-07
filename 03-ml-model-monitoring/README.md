# Project 3: ML Observability & Governance Framework

## ML Observability & Governance

This project implements the operational telemetry and quality control layer. It provides continuous monitoring of both **Graph ML endpoints** (user-item embedding drift, feature attribution metrics) and generative AI configurations (automated prompt regression tests, schema validations, and bias audits).

It explicitly leverages AWS SageMaker tools such as SageMaker Model Monitor for drift and data quality checks, SageMaker Clarify for bias and fairness evaluations, and SageMaker Endpoints for production inference monitoring.

As a part of the Platform:
- **Graph ML Endpoint Monitoring**: Schedules SageMaker Model Monitor jobs that intercept real-time queries and predictions on the GNN (LightGCN) recommendation endpoint (Project 1). It computes drift on the user/item embedding distributions (via custom Population Stability Index checks) and alerts on representation drift.
- **LLM Prompt Regression Testing**: Implements a CI/CD automated validation engine (`prompt_evaluator.py`) running regression evaluations against prompt templates for the support agent (Project 2) before S3 registry release.
- **Bias & Fair Compliance**: Configures SageMaker Clarify jobs to evaluate recommended products for statistical bias (disparate impact metrics) across category slices.
- **Compliance Artifact Generation**: Automatically compiles model card definitions from SageMaker metadata and test suites for operational audits.

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
│      │                    ▼                        ▼              │
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

## LLM Observability & Tracing (Langfuse)

While GNN embedding metrics are monitored via SageMaker Model Monitor, conversational LLM calls and multi-step agent actions are traced using **Langfuse**:
- **Execution Spans**: Every customer transaction or query initiates a trace session in Langfuse, recording prompt inputs, metadata, OpenSearch Serverless KB retrieval matches, LLM completion times, and output tokens.
- **Trace Visualization**: Visualizes the agent's thought process chain (such as the intent classifier routing step, orchestrator lambda, and Bedrock KB tools).
- **Cost Metrics**: Computes active token and dollar-value spend per interaction based on Claude 3.5 Sonnet and Haiku model pricing.

---

## Monitored Metrics

| Metric Category | What's Measured | Alert Threshold |
|----------------|-----------------|-----------------|
| Data Quality | Feature null rates, schema violations, out-of-range values | >2% violation rate |
| Model Quality | Prediction accuracy, F1, AUC vs. baseline | >5% degradation |
| Feature Attribution Drift | SHAP value drift on graph node embeddings from baseline | PSI > 0.2 |
| Data Drift | Input graph degree distribution / embedding shift (KS test, PSI) | PSI > 0.2 |
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

---

## Infrastructure Cost Optimization & Resource Efficiency

To eliminate baseline compute overhead and optimize resources in non-production environments:
- **On-Demand SageMaker Clarify and Model Monitor Scheduling** — Rather than running persistent monitoring clusters, drift detection and weekly bias check jobs are scheduled on-demand using ephemeral `ml.m5.large` processing instances. This ensures compute charges scale to zero immediately after the monitoring run completes.
- **Serverless Alert Dispatching** — Alert metrics and SNS topic endpoints run fully serverless, incurring zero idle billing costs.
- **Langfuse Cloud Observability** — Online LLM evaluations and tracing logs utilize the Langfuse Cloud free tier, avoiding active server cluster management or database licensing costs in dev/sandbox environments.
