# Project 1: Graph AI Recommendation Engine

## Overview

This project powers the product recommendation and discovery experience. It combines a conversational interface using Amazon Bedrock with a graph-based recommendation model running on SageMaker (LightGCN).

The system is designed to be production-ready and integrates with the rest of the platform for training, monitoring, and event tracking.

* **MLOps integration**: The LightGCN model is trained, evaluated, and deployed through the MLOps pipeline in Project 4, using controlled blue/green deployments.
* **Monitoring and governance**: The inference endpoint is continuously monitored for drift and feature distribution changes through the ML monitoring framework in Project 3.
* **Event pipeline**: User interactions and recommendation events are streamed through Kinesis into S3, forming the basis for retraining.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Client Layer                                                  │
│                                                                 │
│  Browser/App ──► API Gateway ──► Lambda Orchestrator          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────────┐
           │               │                   │
           ▼               ▼                   ▼
  ┌─────────────┐  ┌──────────────┐   ┌─────────────────┐
  │ Bedrock     │  │ SageMaker    │   │ Kinesis Stream  │
  │ Agent       │  │ Endpoint     │   │ (events)        │
  │ (Claude 3)  │  │ (LightGCN)   │   │                 │
  └──────┬──────┘  └──────┬───────┘   └────────┬────────┘
         │                │                    │
         │ Action groups  │                    │ Firehose
         ▼                ▼                    ▼
  ProductSearch     Graph inference       S3 Data Lake
         │                                    │
         ▼                                    │ Glue ETL
  OpenSearch (Product KG)                     ▼
                                      SageMaker Feature Store
```

---

## Key Files

| File                                 | Purpose                                                   |
| ------------------------------------ | --------------------------------------------------------- |
| `src/orchestrator.py`                | Lambda entry point that routes requests and calls Bedrock |
| `src/recommendation_model.py`        | Wrapper around SageMaker LightGCN inference               |
| `src/behaviour_tracker.py`           | Sends clickstream events to Kinesis                       |
| `src/guardrails.py`                  | Ensures outputs match the product catalogue               |
| `src/audit_logger.py`                | Logs requests, latency, and model outputs to DynamoDB     |
| `infra/stack.py`                     | CDK infrastructure definition                             |
| `prompts/product_search_v1.2.yaml`   | Versioned prompt template                                 |
| `tests/test_guardrails.py`           | Tests for grounding and validation logic                  |
| `tests/test_recommendation_model.py` | Tests for inference validation                            |

---

## Setup

```bash
pip install -r requirements.txt

# Run tests (with mocked AWS services)
python -m pytest tests/ -v

# Deploy infrastructure
cd infra && cdk deploy LegoRecommendationStack
```

---

## Governance and Guardrails

* **Input validation**: All inputs are validated using structured schemas before reaching the model or agent.
* **Output grounding**: Recommendations are checked against the product catalogue. Invalid or unknown product IDs are filtered out.
* **Audit logging**: Each request is logged with inputs, outputs, metadata, and latency.
* **Prompt versioning**: Prompts are stored in S3 with versioning to ensure changes are controlled and traceable.

---

## Cost and Efficiency

The system is designed to scale down in development and testing environments:

* **SageMaker serverless endpoints** scale to zero when idle, so non-production usage is effectively near-zero cost.
* **Bedrock usage** is pay-per-token, so costs only appear during active requests.
* **Local development** uses mocked AWS services (moto/LocalStack), avoiding cloud costs during testing.

---
