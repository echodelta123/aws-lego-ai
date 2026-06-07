# Project 1: Graph AI Recommendation Engine

## Overview & Graph AI Architecture

This project implements the product discovery and recommendation engine. It integrates a conversational AI with a Graph Machine Learning model ( **Amazon Bedrock agent** connected to a **SageMaker Graph Collaborative Filtering (LightGCN) model**) to generate personalized product recommendations.

The architecture is built for production operations:
- **MLOps Pipeline Integration**: The Graph Neural Network (LightGCN) recommendation model is automatically trained, evaluated, and registered via the [MLOps Production Pipeline (Project 4)](../04-mlops-production-pipeline/README.md) and served through a blue/green endpoint deployment.
- **ML Observability Integration**: The deployed real-time inference endpoint is continuously audited for feature attribution drift (SHAP value shifts) and embedding distribution drift via the [ML Model Monitoring & Governance Framework (Project 3)](../03-ml-model-monitoring/README.md).
- **Behavioral Event Pipeline**: User clickstream events and model recommendation states are streamed via Amazon Kinesis into an S3 Data Lake, providing the raw edges and nodes required for retraining runs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Client-Facing Orchestration Layer                              │
│                                                                 │
│  Browser/App ──► API Gateway ──► Lambda Orchestrator           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────────┐
           │               │                   │
           ▼               ▼                   ▼
  ┌─────────────┐  ┌──────────────┐   ┌─────────────────┐
  │  Bedrock    │  │  SageMaker   │   │  Kinesis Data   │
  │  Agent      │  │  Endpoint    │   │  Stream         │
  │  (Claude 3) │  │  (LightGCN)  │   │  (events)       │
  └──────┬──────┘  └──────┬───────┘   └────────┬────────┘
         │                │                     │
         │  Action Groups │                     │ Firehose
         │  ┌─────────────┘                     ▼
         │  │                          ┌─────────────────┐
         │  ▼                          │  S3 Data Lake   │
         │  ProductSearch              └────────┬────────┘
         │  GraphLookup                         │ Glue ETL
         │  CatalogueValidator                  ▼
         │                            ┌─────────────────┐
         │  Knowledge Base            │  SageMaker      │
         │  └──► OpenSearch Serverless│  Feature Store  │
         │         (Product KG)       └─────────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/orchestrator.py` | Lambda entrypoint — routes requests, validates inputs, calls Bedrock Agent |
| `src/recommendation_model.py` | SageMaker model wrapper — input schema validation, inference, GNN output scoring |
| `src/behaviour_tracker.py` | Publishes clickstream events to Kinesis with schema enforcement |
| `src/guardrails.py` | Grounding guardrail — validates agent outputs against a catalogue registry |
| `src/audit_logger.py` | Writes model I/O, latency, and decision context to DynamoDB audit table |
| `infra/stack.py` | CDK stack defining all AWS resources |
| `prompts/product_search_v1.2.yaml` | Versioned prompt template for the product search action |
| `tests/test_guardrails.py` | Unit tests for catalogue grounding logic |
| `tests/test_recommendation_model.py` | Unit tests for inference input validation |

---

## Setup

```bash
pip install -r requirements.txt
# Run unit tests with mocked AWS services (moto)
python -m pytest tests/ -v

# Deploy to AWS (requires configured credentials)
cd infra && cdk deploy LegoRecommendationStack
```

---

## Governance & Guardrails

- **Schema Validation**: Inputs are validated via Pydantic models before reaching the Bedrock agent or SageMaker endpoint.
- **Output Grounding**: Agent recommendations are cross-checked against the DynamoDB product catalogue. Any product code not found in the catalogue is removed to prevent hallucinations from reaching client apps.
- **Audit Logging**: Every invocation registers a request ID, inputs, raw embeddings metadata, scores, and execution latency.
- **Immutable Prompts**: Prompts are stored in S3 using semantically versioned directories, preventing manual inline prompt overrides in production.

---

## Cost Optimization & Resource Efficiency

To optimize non-production environments and prevent baseline compute overhead, the service employs:
- **SageMaker Serverless Endpoints**: The GNN inference endpoint runs serverless, scaling down to 0 concurrency when idle. Non-production environments run at **$0.00/month** baseline, billing only per-millisecond of execution time during active testing.
- **Pay-Per-Token LLM Billing**: Amazon Bedrock invokes Claude 3 Sonnet dynamically, scaling to zero costs when idle. Active testing averages **<$1.00/month**.
- **Local Profile Mocking**: Local testing routes clickstream events and catalog interactions through `moto`/LocalStack, completely bypassing AWS ingestion charges.
